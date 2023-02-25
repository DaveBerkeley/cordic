#!/bin/env python3

import argparse

from enum import IntEnum, unique

from amaranth import *
from amaranth.build import *

from cordic import CordicRotate

from pll import get_pll
from spi import SpiInit

#
#

from amaranth_boards.ulx3s import ULX3S_85F_Platform as Platform

#
#

adc_init = [
    0x0806, # ADC Mode control
    0x1000, # ADC Config Reg (0x1004 for echo)
    0x9800, # Range
    0x8800, # UniPolar
    0x9000, # BiPolar
]

class ADC(SpiInit):

    def __init__(self, init=adc_init, divider=1):
        SpiInit.__init__(self, width=16, init=init, divider=divider)

#
#   AD5628 12-bit SPI DAC

dac_init = [
    0xf80000ff, # cmd=C_REF enable external reference
]

class DAC(SpiInit):

    def __init__(self, init=dac_init, divider=1):
        SpiInit.__init__(self, width=32, init=init, divider=divider)
    
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

        self.dac = DAC(divider=1)

        self.clock_speed = 100e6
        self.samples = 32
        self.us = 40e3
        self.period = int(self.clock_speed / (self.us * self.samples))
        self.sample_period = Signal(range(self.period))
        self.phase = Signal(self.cwidth)

        # swept freq generator
        self.note = Signal(range(4))
        self.octave = Signal(range(16))
        self.theta = Signal(range(12 + 16))

        self.state = Signal(State, reset=State.IDLE)

    def elaborate(self, platform):
        m = Module()

        m.submodules += self.dac
        m.submodules += self.cordic

        self.add_spi_dac(m, platform)

        self.set_clock(m, platform, self.clock_speed)

        #for i in range(8):
        #    s = platform.request("led", i)
        #    try:
        #        m.d.sync += s.eq(self.sample_period[i])
        #    except IndexError:
        #        break

        m.d.sync += [
            self.sample_period.eq(self.sample_period + 1),
        ]

        with m.If(self.sample_period == (self.period - 1)):
            m.d.sync += self.sample_period.eq(0)

        #x0 = int(self.cordic.X0 * 0.25)
        x0 = int(self.cordic.X0 * 1.0)
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

        cmd = 0xf300_00ff
        m.d.comb += self.dac.data.eq(cmd + ((0xfff & self.cordic.x) << 8))

        with m.If(self.cordic.ready & self.dac.ready & (self.state == State.CORDIC)):
            # Tx command
            m.d.sync += self.dac.start.eq(1)

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

        self.add_passthru(m, platform)

        return m

    def add_passthru(self, m, platform):
        #
        # see
        # https://github.com/emard/ulx3s-misc/blob/master/examples/esp32_passthru/proj/hdl/esp32_passthru.v
        #
        io = [
            Resource('ftdi', 0,
                Subsignal('txd', Pins("M1", dir="i")),
                Subsignal('rxd', Pins("L4", dir="o")),
                Subsignal('nrts', Pins("M3", dir="i")),
                Subsignal('ndtr', Pins("N1", dir="i")),
                Attrs(IO_TYPE="LVCMOS33")
            ),
            Resource('wifi', 0,
                Subsignal('txd', Pins("K4", dir="i")),
                Subsignal('rxd', Pins("K3", dir="o")),
                Subsignal('en', Pins("J5", dir="o")),
                Subsignal('gpio0', Pins("F1", dir="o")),
                Attrs(IO_TYPE="LVCMOS33")
            ),
            #Resource('gpio', 2, Pins("J3", dir="o"), Attrs(IOSTANDARD="LVCMOS33")),
            #Resource('gpio', 4, Pins("H1", dir="o"), Attrs(IOSTANDARD="LVCMOS33")),
            #Resource('gpio', 5, Pins("U5", dir="o"), Attrs(IOSTANDARD="LVCMOS33")),
            #Resource('gpio', 23, Pins("R5", dir="o"), Attrs(IOSTANDARD="LVCMOS33")),
        ]
        platform.add_resources(io)

        wifi = platform.request("wifi", 0)
        ftdi = platform.request("ftdi", 0)

        m.d.comb += [
            wifi.rxd.eq(ftdi.txd),
            ftdi.rxd.eq(wifi.txd),
        ]

        state = Cat(ftdi.nrts, ftdi.ndtr)

        with m.Switch(state):
            with m.Case(3):
                m.d.comb += [ wifi.en.eq(1), wifi.gpio0.eq(1), ]
            with m.Case(0):
                m.d.comb += [ wifi.en.eq(1), wifi.gpio0.eq(1), ]
            with m.Case(2):
                m.d.comb += [ wifi.en.eq(0), wifi.gpio0.eq(1), ]
            with m.Case(1):
                m.d.comb += [ wifi.en.eq(1), wifi.gpio0.eq(0), ]

        #gpio2 = platform.request("gpio", 2)
        #m.d.comb += gpio2.eq(wifi.gpio0)

        m.d.comb += [
            platform.request("led", 0).eq(~wifi.rxd),
            platform.request("led", 1).eq(~ftdi.rxd),
            platform.request("led", 2).eq(~wifi.gpio0),
            platform.request("led", 3).eq(~wifi.en),
            platform.request("led", 4).eq(~ftdi.nrts),
            platform.request("led", 5).eq(~ftdi.ndtr),
        ]

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
            def __init__(self, idx=0):
                self.cs   = platform.request("dac.cs", idx)
                self.copi = platform.request("dac.copi", idx)
                self.clk  = platform.request("dac.clk", idx)
                self.ldac = platform.request("dac.ldac", idx)

        spi = SPI(0)

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
