#!/bin/env python3

from amaranth import *
from amaranth.sim import *

from amaranth.utils import bits_for

#
#

class Boxcar(Elaboratable):

    def __init__(self, width=None, N=None):
        self.N = N
        assert N == (1 << bits_for(N-1)), "N must be power of 2"
        self.i = Signal(signed(width))
        self.o = Signal(signed(width))

        self.addr = Signal(range(N))
        self.sum = Signal(signed(width + bits_for(N)))

        self.start = Signal()
        self.ready = Signal(reset=1)

        self.mem = Memory(width=width, depth=N)
        self.oldest = Signal(signed(width))

        self.state = Signal(2)

    def elaborate(self, platform):
        m = Module()

        rd = self.mem.read_port(transparent=False)
        wr = self.mem.write_port()
        m.submodules += rd
        m.submodules += wr

        m.d.comb += [
            rd.addr.eq(self.addr),
            wr.addr.eq(self.addr),
            rd.en.eq(1),
        ]

        with m.If(self.start & (self.state == 0)):

            m.d.sync += [
                self.state.eq(1),
                self.ready.eq(0),
                self.sum.eq(self.sum + self.i),
                self.oldest.eq(rd.data),
            ]

        with m.If(self.state == 1):

            m.d.sync += [
                self.state.eq(2),
                self.sum.eq(self.sum - self.oldest),
                wr.en.eq(1),
                wr.data.eq(self.i),
            ]

        with m.If(self.state == 2):

            m.d.sync += [
                self.state.eq(0),
                wr.en.eq(0),
                self.o.eq(self.sum >> bits_for(self.N)),
                self.ready.eq(1),
                self.addr.eq(self.addr + 1),
            ]

        return m

    def ports(self):
        return [
            self.i, self.o,
            self.start, self.ready,
        ]

#
#

def sim(m):

    sim = Simulator(m)

    def tick(n=1):
        assert n
        for i in range(n):
            yield Tick()

    def sample(s):

        while True:
            d = yield m.ready
            if d:
                break
            yield from tick()

        yield m.i.eq(s)
        yield m.start.eq(1)
        yield from tick()
        yield m.start.eq(0)

        while True:
            d = yield m.ready
            if not d:
                break
            yield from tick()

    def proc():

        yield from tick(2)

        for i in range(17):
            yield from sample(0x10 * i)

        yield from tick(100)

    sim.add_clock(1 / 100e6)
    sim.add_sync_process(proc)
    with sim.write_vcd("boxcar.vcd", traces=m.ports()):
        sim.run()

#
#

if __name__ == "__main__":

    dut = Boxcar(width=12, N=8)
    sim(dut)


# FIN
