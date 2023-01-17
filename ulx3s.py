#!/bin/env python3

import argparse

from amaranth import *

from cordic import CordicCore

from pll import get_pll

#
#

class Application(Elaboratable):

    def __init__(self):
        self.counter = Signal(32)

    def set_clock(self, m, platform, freq):
        PLL = get_pll(platform)
        xtal_freq = platform.default_clk_frequency
        self.freq = freq
        self.pll = PLL(xtal_freq, self.freq)

        m.submodules += self.pll

        clk_i = platform.request(platform.default_clk).i

        cd_name = "sync"
        cd = ClockDomain(cd_name)

        m.domains += cd

        m.d.comb += [
            self.pll.clkin.eq(clk_i),
            ClockSignal(cd_name).eq(self.pll.clkout),
        ]

    def elaborate(self, platform):
        m = Module()

        self.set_clock(m, platform, 250e6)

        m.d.sync += [
            self.counter.eq(self.counter + 1),
        ]

        for i in range(8):
            s = platform.request("led", i)
            m.d.comb += [
                s.eq(self.counter[i + 20]),
            ]

        return m

#
#

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--prog", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    dut = Application()

    from amaranth_boards.ulx3s import ULX3S_85F_Platform as Platform
    platform = Platform()

    #pll = get_pll(platform)
    #print(platform.default_clk, platform.default_clk_frequency)
    #print(pll.calc(platform.default_clk_frequency, 200e6))
    #help(pll)
    
    platform.build(dut, do_program=args.prog, verbose=args.verbose)
    

# FIN
