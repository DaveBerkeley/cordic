#!/bin/env python3

from amaranth import *

#
#

def get_clock_freq(platform):
    n = platform.default_clk
    c = platform.resources[(n, 0)]
    f = c.clock.frequency
    print("system clock freq", f)
    return f

#
#   ECP5 PLL

class ECP5PLL(Elaboratable):
    clki_div_range  = (1, 128+1)
    #clkfb_div_range = (1, 128+1)
    clko_div_range  = (1, 128+1)
    clki_freq_range = (    8e6,  400e6)
    clko_freq_range = (3.125e6,  400e6)
    vco_freq_range  = (  400e6,  800e6)
    pfd_freq_range  = (   10e6,  400e6)

    clkfb_div_range = (1, 80+1) # See FPGA Libraries Reference Guide p280
    # Values taken from ecppll source
    clki_freq_range = (8e6, 400e6)
    clko_freq_range = (10e6, 400e6)
    vco_freq_range  = (400e6, 800e6)
    pfd_freq_range  = (3.125e6, 400e6)

    @classmethod
    def in_range(cls, n, r):
        return r[0] <= n <= r[1]

    @classmethod
    def get_vco(cls, ifreq, d, fb, od):
        vco = (ifreq / d) * fb * od
        if not cls.in_range(vco, cls.vco_freq_range):
            return None
        return vco

    @classmethod
    def check(cls, ifreq, d, fb, od):
        pfd = ifreq / d
        if not cls.in_range(pfd, cls.pfd_freq_range):
            return False
        vco = cls.get_vco(ifreq, d, fb, od)
        if vco is None:
            return False
        ofreq = vco / od
        if not cls.in_range(ofreq, cls.clko_freq_range):
            return False
        return True

    @classmethod
    def calc(cls, ifreq, ofreq, verbose=False):
        error = ifreq + 1
        config = None
        for clki_div in range(*cls.clki_div_range):
            for clkfb_div in range(*cls.clkfb_div_range):
                for clkp_div in range(*cls.clko_div_range):

                    if not cls.check(ifreq, clki_div, clkfb_div, clkp_div):
                        continue
                    vco_freq = cls.get_vco(ifreq, clki_div, clkfb_div, clkp_div)
                    assert vco_freq

                    # Using CLKOP to allow a wider range of ratios,
                    # but taking the clock from CLKOS gives more flexible solutions.
                    for clks_div in range(*cls.clko_div_range):

                        clk_freq = vco_freq / clks_div

                        if not cls.in_range(clk_freq, cls.clko_freq_range):
                            continue

                        e = abs(clk_freq - ofreq)
                        if e > error:
                            continue
                        error = e

                        config = {
                            "ifreq"     : ifreq, 
                            "ofreq"     : vco_freq / clks_div, 
                            "xfreq"     : vco_freq / clkp_div,
                            "clki_div"  : clki_div, 
                            "clkfb_div" : clkfb_div, 
                            "clko0_div" : clkp_div, 
                            "clko1_div" : clks_div, 
                            "vco"       : vco_freq,
                        }

                        if error == 0:
                            break

        if verbose:
            print(cls.__name__, config)
        assert error == 0, config
        return config

    def __init__(self, ifreq, ofreq):
        assert self.in_range(ifreq, self.clki_freq_range), (ifreq, self.clki_freq_range)
        assert self.in_range(ofreq, self.clko_freq_range), (ofreq, self.clko_freq_range)

        self.clkin = Signal()
        self.clko_p = Signal()
        self.clko_s = Signal()
        self.clkout = Signal()
        self.locked = Signal()
        self.rst = Signal()
        self.stdby = Signal()

        config = self.calc(ifreq, ofreq, verbose=True)

        params = {}

        params.update(
            i_RST       = self.rst,
            i_CLKI      = self.clkin,
            i_STDBY     = self.stdby,
            o_LOCK      = self.locked,
            p_CLKFB_DIV = config["clkfb_div"],
            p_CLKI_DIV  = config["clki_div"],
            p_FEEDBK_PATH = "INT_OP"
        )

        n_to_l = {0: "P", 1: "S", 2: "S2", 3: "S3"}

        for n in range(2):
            div = config[f"clko{n}_div"]
            params[f"p_CLKO{n_to_l[n]}_ENABLE"] = "ENABLED"
            params[f"p_CLKO{n_to_l[n]}_DIV"]    = div
            params[f"p_CLKO{n_to_l[n]}_FPHASE"] = 0
            params[f"p_CLKO{n_to_l[n]}_CPHASE"] = 0

        params["o_CLKOP"] = self.clko_p
        params["o_CLKOS"] = self.clko_s

        params.update(
            a_FREQUENCY_PIN_CLKI = str(int(ifreq/1e6)),
            a_FREQUENCY_PIN_CLKOP = str(int(config["xfreq"]/1e6)),
            a_FREQUENCY_PIN_CLKOS = str(int(ofreq/1e6)),
            # These params from ecppll
            #a_ICP_CURRENT = "12",
            #a_LPF_RESISTOR = "8",
            #a_MFG_ENABLE_FILTEROPAMP = "1",
            #a_MFG_GMCREF_SEL = "2"
            # These params from litex
            a_ICP_CURRENT = "6",
            a_LPF_RESISTOR = "16",
            a_MFG_ENABLE_FILTEROPAMP = "1",
            a_MFG_GMCREF_SEL = "2"
        )

        #for k, v in params.items():
        #    print(k, v)
        self.pll = Instance("EHXPLLL", **params)        

    def elaborate(self, platform):
        m = Module()
        m.submodules += self.pll

        m.d.comb += [
            self.clkout.eq(self.clko_s),
        ]

        return m

    def ports(self):
        return [ self.clkout, self.clkin, self.locked, self.rst, ]

#
#   Test 

v = __name__ == "__main__"

if v:
    for c in [ ECP5PLL ]:
        c.calc(48e6, 200e6, verbose=v)
        c.calc(50e6, 200e6, verbose=v)
        c.calc(48e6, 50e6, verbose=v)
        c.calc(48e6, 124e6, verbose=v)
        c.calc(50e6, 124e6, verbose=v)

        c.calc(33e6, 48e6, verbose=v)
        c.calc(50e6, 48e6, verbose=v)
        c.calc(25e6, 400e6, verbose=v)

    ECP5PLL.calc(25e6, 200e6, verbose=v)

#
#

def get_pll(platform):

    if platform.device in [ "LFE5U-25F", "LFE5U-45F", "LFE5U-85F" ]:
        return ECP5PLL

    raise Exception(platform.device)

#   FIN

