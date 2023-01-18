#!/bin/env python3

import argparse

from amaranth import *
from amaranth.build import *

from cordic import CordicCore

from pll import get_pll
from ad5628 import DAC

#
#

from amaranth_boards.ulx3s import ULX3S_85F_Platform as Platform

#
#

class Application(Elaboratable):

    def __init__(self):
        self.counter = Signal(32)

        self.cwidth = 8
        self.cordic = CordicCore(a_width=self.cwidth, o_width=self.cwidth)

        self.dac = DAC()

    def elaborate(self, platform):
        m = Module()

        self.add_spi_dac(m, platform)
        m.submodules += self.dac

        self.set_clock(m, platform, 10e6)

        m.d.sync += [
            self.counter.eq(self.counter + 1),
        ]

        output = Signal(8)

        with m.If(self.cordic.ready):
            m.d.sync += output.eq(self.cordic.z)

        for i in range(8):
            s = platform.request("led", i)
            m.d.sync += [
                #s.eq(self.counter[i + 20]),
                s.eq(output[i] + 0x7f),
            ]

        m.submodules += self.cordic

        x0 = int(0.99 * self.cwidth / (self.cordic.K * 2))

        m.d.comb += [
            self.cordic.x0.eq(x0),
            self.cordic.y0.eq(0),
        ]

        shift = 21
        shifted = Signal(self.cwidth+1)

        m.d.comb += shifted.eq(self.counter >> shift)

        for i in range(self.cwidth):
            m.d.comb += [
                self.cordic.z0[i].eq(shifted[i+1]),
            ]

        start = Signal(4)
        m.d.comb += start.eq(shifted[0])
        m.d.sync += self.cordic.start.eq(start)

        # SPI DAC

        dac_state = Signal(2)

        with m.If(self.dac.ready & ~self.dac.start):
            # Tx command
            m.d.sync += self.dac.start.eq(1)

            with m.If(dac_state == 0):
                m.d.sync += [
                    self.dac.cmd.eq(self.dac.C_RESET),
                    self.dac.addr.eq(0),
                    self.dac.data.eq(0),
                    dac_state.eq(1),
                ]

            with m.If(dac_state == 1):
                m.d.sync += [
                    self.dac.cmd.eq(self.dac.C_REF),
                    self.dac.addr.eq(0),
                    self.dac.data.eq(1),
                    dac_state.eq(2),
                ]

        with m.If(self.dac.start):
            m.d.sync += [
                self.dac.start.eq(0),
                self.dac.cmd.eq(self.dac.C_CONVERT),
                # TODO : send real data
                self.dac.data.eq(self.dac.data + 1),
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
