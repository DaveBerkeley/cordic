#!/bin/env python3

from amaranth import *
from amaranth.sim import *

#
#

class SPI(Elaboratable):

    def __init__(self, width, divider=1):
        self.width = width
        # Outputs
        self.cs = Signal()
        self.copi = Signal()
        self.sck = Signal(reset=1)

        self.start = Signal()
        self.ready = Signal(reset=1)

        # Data in
        self.data = Signal(width)

        # SPI interface
        self.sro = Signal(width)
        self.bit = Signal(range(width))

        self.divider = divider
        self.ck_gen = Signal(range(divider))
        self.ck_change = Signal()

    def elaborate(self, platform):
        m = Module()

        m.d.comb += self.copi.eq(self.sro[self.width-1])

        if self.divider > 1:
            m.d.sync += self.ck_gen.eq(self.ck_gen + 1)

        m.d.comb += self.ck_change.eq(self.ck_gen == 0)

        with m.If(self.ready):
            # end cs period
            m.d.sync += self.cs.eq(0)

        with m.If(self.start):
            # begin transfer
            m.d.sync += [
                self.bit.eq(self.width-1),
                self.ready.eq(0),

                self.cs.eq(1),
                self.sro.eq(self.data),
            ]

        with m.If(self.cs & self.ck_change):
            # running
            with m.If(~self.ready):
                m.d.sync += self.sck.eq(~self.sck)

            with m.If(~self.sck):
                m.d.sync += [
                    self.sro.eq(self.sro << 1),
                    self.bit.eq(self.bit - 1),
                ]

                with m.If(self.bit == 0):
                    # done
                    m.d.sync += self.ready.eq(1)

        return m

    def ports(self):
        return [
            self.data,
            self.copi, self.cs, self.sck,
            self.start, self.ready,
        ]

#
#

class SpiInit(Elaboratable):

    def __init__(self, width=16, init=[], divider=1):
        self.spi = SPI(width=width, divider=divider)

        self.cs = Signal()
        self.sck = Signal()
        self.copi = Signal()
        self.ready = Signal()
        self.start = Signal()
        self.data = Signal(width)

        self.init = Array([ Const(x) for x in init ])

        self.do_init = Signal(reset=1)
        self.init_idx = Signal(range(len(self.init)+1))
        self.init_start = Signal()

    def elaborate(self, platform):
        m = Module()

        m.submodules += self.spi

        # connect the SPI signals
        m.d.comb += [
            self.cs.eq(self.spi.cs),
            self.sck.eq(self.spi.sck),
            self.copi.eq(self.spi.copi),
        ]

        # connect start/ready/data depnding on init state
        with m.If(self.do_init):
            m.d.comb += [
                self.spi.start.eq(self.init_start),
                self.spi.data.eq(self.init[self.init_idx]),
                self.ready.eq(0),
            ]
        with m.Else():
            m.d.comb += [
                self.spi.start.eq(self.start),
                self.spi.data.eq(self.data),
                self.ready.eq(self.spi.ready),
            ]

        # send init commands to device
        with m.If(self.do_init):
            with m.If(self.init_start):
                m.d.sync += [
                    self.init_start.eq(0),
                    self.init_idx.eq(self.init_idx + 1),
                ]

            with m.If(self.spi.ck_change & self.spi.ready & ~self.spi.start):
                m.d.sync += self.init_start.eq(1)

            with m.If(self.init_idx == len(self.init)):
                m.d.sync += self.do_init.eq(0)

        return m

    def ports(self):
        return self.spi.ports()

#
#   Class used by simulation to read spi serial data

class IO:

    def __init__(self, width):
        self.width = width
        self.ck = 0
        self.sr = []
        self.bit = 0
        self.cs = 0
        self.rx = []

    def reset(self):
        # start of word
        self.ck = 0
        self.sr = []
        self.bit = 0

    def poll(self, cs, ck, d):
        if cs != self.cs:
            if cs:
                # start of word
                self.reset()
            else:
                # end of word
                data = 0
                for i in range(self.width):
                    data <<= 1
                    if self.sr[i]:
                        data |= 1
                self.rx.append(data)
                self.reset()
        self.cs = cs

        if cs and (ck != self.ck):
            # -ve edge of clock
            if not ck:
                self.bit += 1
                self.sr.append(d)
        self.ck = ck

#
#

def sim(m):
    sim = Simulator(m)

    do = IO(m.width)

    def tick(n=1):
        assert n
        for i in range(n):
            yield Tick()

            # Rx SPI data
            cs = yield m.cs
            ck = yield m.sck
            d = yield m.copi
            do.poll(cs, ck, d)

    def wait_ready():
        while True:
            yield from tick()
            r = yield m.ready
            if r:
                break

    def tx(data):
        yield from wait_ready()
        yield from tick()
        yield m.start.eq(1)
        yield m.data.eq(data)
        yield from tick()
        yield m.start.eq(0)

        yield from tick()

    def proc():
        yield from tick(5)

        def cat(data, addr, cmd):
            return 0xf000_0000 + (cmd << 24) + (addr << 20) + (data << 8) + 0xff

        C_REF, C_CONVERT = 0x8, 0x3
        cmds = [
            cat(0x1,   0xa, C_REF),
            cat(0x123, 0x1, C_CONVERT),
            cat(0xabc, 0x2, C_CONVERT),
            cat(0xfff, 0x4, C_CONVERT),
            cat(0x000, 0x8, C_CONVERT),
        ]

        for d in cmds:
            yield from tx(d)
        yield from wait_ready()
        yield from tick()

        for i, d in enumerate(cmds):
            # check we output the correct data
            assert do.rx[i] == d, (i, state, hex(do.rx[i]), hex(d))

        yield from tick(5)

    sim.add_clock(1 / 100e6)
    sim.add_sync_process(proc)
    with sim.write_vcd("spi.vcd", traces=m.ports()):
        sim.run()

#
#

if __name__ == "__main__":
    dut = SPI(width=32)
    sim(dut)

#   FIN
