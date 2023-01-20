#!/bin/env python3

import argparse

from enum import IntEnum, unique

from amaranth import *
from amaranth.build import *

from cordic import CordicRotate

from pll import get_pll
from ad5628 import DAC

#
#

from amaranth_boards.ulx3s import ULX3S_85F_Platform as Platform

#
#

class State(IntEnum):

    IDLE = 0
    CORDIC = 1
    DAC = 2

class Application(Elaboratable):

    def __init__(self):
        self.cwidth = 12
        self.cordic = CordicRotate(a_width=self.cwidth, o_width=self.cwidth)

        self.dac = DAC()

        self.clock_speed = 100e6
        self.samples = 32
        self.us = 40e3
        self.period = int(self.clock_speed / (self.us * self.samples))
        self.sample_period = Signal(range(self.period))
        self.phase = Signal(self.cwidth)

        self.state = Signal(State, reset=State.IDLE)

    def elaborate(self, platform):
        m = Module()

        m.submodules += self.dac
        m.submodules += self.cordic

        self.add_spi_dac(m, platform)

        self.set_clock(m, platform, self.clock_speed)

        for i in range(8):
            s = platform.request("led", i)
            try:
                m.d.sync += s.eq(self.sample_period[i])
            except IndexError:
                break

        m.d.sync += [
            self.sample_period.eq(self.sample_period + 1),
        ]

        with m.If(self.sample_period == (self.period - 1)):
            m.d.sync += self.sample_period.eq(0)

        x0 = self.cordic.X0
        offset = (1 << self.cwidth) >> 1
        step = 1 << 7

        with m.If(self.sample_period == 0):

            # start sine generation
            m.d.sync += [
                self.cordic.x0.eq(x0),
                self.cordic.y0.eq(0),
                self.cordic.z0.eq(self.phase),
                self.cordic.offset.eq(offset),
                self.cordic.start.eq(1),
                self.phase.eq(self.phase + step),
            ]

        with m.If(self.cordic.start):
            m.d.sync += [
                self.cordic.start.eq(0),
                self.state.eq(State.CORDIC),
            ]

        # SPI DAC

        dac_init = Signal(reset=1)

        with m.If(self.cordic.ready & self.dac.ready & (self.state == State.CORDIC)):
            # Tx command
            m.d.sync += self.dac.start.eq(1)

            with m.If(dac_init):
                m.d.sync += [
                    self.dac.cmd.eq(self.dac.C_REF),
                    self.dac.addr.eq(0),
                    self.dac.data.eq(0),
                    dac_init.eq(0),
                ]

            with m.Else():
                m.d.sync += [
                    self.dac.cmd.eq(self.dac.C_CONVERT),
                    self.dac.addr.eq(0),
                    self.dac.data.eq(self.cordic.x),
                ]

        with m.If(self.dac.start):
            m.d.sync += [
                self.dac.start.eq(0),
                self.state.eq(State.DAC),
            ]

        with m.If((self.state == State.DAC) & self.dac.ready):
            m.d.sync += self.state.eq(State.IDLE)

        # Test outputs to logic analyser

        r = [
            # Use connector ("gpio",0) to define PMOD SPI DAC Peripheral
            Resource("test", 0, Pins("gpio_0:3+", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
            Resource("test", 1, Pins("gpio_0:2+", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
            Resource("test", 2, Pins("gpio_0:0+", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
            Resource("test", 3, Pins("gpio_0:1+", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
        ]

        platform.add_resources(r)

        m.d.comb += [
            platform.request("test", 0).eq(self.sample_period == 0),
            platform.request("test", 1).eq(self.cordic.start),
            platform.request("test", 2).eq(self.cordic.ready),
            platform.request("test", 3).eq(self.dac.ready),

            #platform.request("test", 0).eq(self.cordic.start),
            #platform.request("test", 0).eq(self.cordic.x[0]),
            #platform.request("test", 1).eq(self.cordic.x[1]),
            #platform.request("test", 2).eq(self.cordic.x[2]),
            #platform.request("test", 3).eq(self.cordic.x[3]),
        ]

        return m

    def set_clock(self, m, platform, freq, cd_name="sync"):
        PLL = get_pll(platform)
        xtal_freq = platform.default_clk_frequency
        self.freq = freq
        self.pll = PLL(xtal_freq, self.freq)

        m.submodules += self.pll

        clk_i = platform.request(platform.default_clk).i

        cd = ClockDomain(cd_name)

        m.domains += cd

        m.d.comb += [
            self.pll.clkin.eq(clk_i),
            ClockSignal(cd_name).eq(self.pll.clkout),
        ]

    def add_spi_dac(self, m, platform):

        r = [
            # Use connector ("gpio",0) to define PMOD SPI DAC Peripheral
            Resource("dac.cs",   0, Pins("gpio_0:3-", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
            Resource("dac.copi", 0, Pins("gpio_0:2-", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
            Resource("dac.clk",  0, Pins("gpio_0:0-", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
            Resource("dac.ldac", 0, Pins("gpio_0:1-", dir="o"), Attrs(IO_TYPE="LVCMOS33")),
        ]

        platform.add_resources(r)

        class SPI:            
            cs   = platform.request("dac.cs", 0)
            copi = platform.request("dac.copi", 0)
            clk  = platform.request("dac.clk", 0)
            ldac = platform.request("dac.ldac", 0)

        spi = SPI()

        # connect DAC to SPI bus

        m.d.comb += [
            spi.cs.eq(~self.dac.cs),
            spi.copi.eq(self.dac.copi),
            spi.clk.eq(self.dac.sck),
            spi.ldac.eq(0),
        ]

#
#

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--prog", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    dut = Application()

    platform = Platform()

    platform.build(dut, do_program=args.prog, verbose=args.verbose)

# FIN
