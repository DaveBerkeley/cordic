#!/bin/env python3

from amaranth import *
from amaranth.sim import *

from spi import SpiInit, IO

#
#   Driver for SPI 12-bit 8-channel DAC
#
#   https://digilent.com/reference/_media/pmod:pmod:pmodDA4_RM.pdf
#

class DAC(Elaboratable):

    C_REF = 0x8
    C_CONVERT = 0x3
    C_RESET = 0x7

    def __init__(self, init, divider):

        self.spi = SpiInit(width=32, init=init, divider=divider)

        # Outputs
        self.cs = Signal()
        self.copi = Signal()
        self.sck = Signal(reset=1)

        self.data = Signal(12)
        self.addr = Signal(4)
        self.cmd = Signal(4)

        self.start = Signal()
        self.ready = Signal(reset=1)

    def elaborate(self, platform):
        m = Module()

        m.submodules += self.spi

        # pad the 32-bit word with unused sections
        top = Const(0xf, 4)
        tail = Const(0xff, 8)

        # connect to the SPI submodule
        m.d.comb += [
            self.sck.eq(self.spi.sck),
            self.cs.eq(self.spi.cs),
            self.copi.eq(self.spi.copi),

            self.spi.start.eq(self.start),
            self.ready.eq(self.spi.ready),
            self.spi.data.eq(Cat(tail, self.data, self.addr, self.cmd, top)),
        ]

        return m

    def ports(self):
        return [
            self.cs, self.copi, self.sck,
            self.data, self.addr, self.cmd,
            self.start, self.ready,
        ]

#
#

def sim(m, init, divider):
    sim = Simulator(m)

    io = IO(32)

    def tick(n=1):
        assert n
        for i in range(n):
            yield Tick()

            # Rx SPI data
            cs = yield m.cs
            ck = yield m.sck
            d = yield m.copi
            io.poll(cs, ck, d)

    def wait_ready():
        while True:
            yield from tick()
            r = yield m.ready
            if r:
                break

    def tx(data, addr, cmd):
        yield from wait_ready()
        yield from tick(divider)
        yield m.start.eq(1)
        yield m.data.eq(data)
        yield m.addr.eq(addr)
        yield m.cmd.eq(cmd)
        yield from tick()
        yield m.start.eq(0)

    def proc():
        yield from tick(25)

        cmds = [
            (0x1,   0xa, DAC.C_REF),
            (0x123, 0x1, DAC.C_CONVERT),
            (0xabc, 0x2, DAC.C_CONVERT),
            (0xfff, 0x4, DAC.C_CONVERT),
            (0x000, 0x8, DAC.C_CONVERT),
        ]

        for cmd in cmds:
            yield from tx(*cmd)
        yield from wait_ready()
        yield from tick()

        test = [
            0xf8a001ff,
            0xf31123ff,
            0xf32abcff,
            0xf34fffff,
            0xf38000ff,
        ]

        for i, d in enumerate(init + test):
            assert io.rx[i] == d, (i, hex(io.rx[i]), hex(d))

        yield from tick(5)

    sim.add_clock(1 / 100e6)
    sim.add_sync_process(proc)
    with sim.write_vcd("ad5628.vcd", traces=m.ports()):
        sim.run()

#
#

if __name__ == "__main__":
    init = [
        0x12345678,
    ]
    divider = 16
    dut = DAC(init, divider)
    sim(dut, init, divider)
# FIN
