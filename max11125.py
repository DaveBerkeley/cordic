#!/bin/env python3

#   Driver for the 12-bit 1M s/s ADC found on the ulx3s
#

from amaranth import *
from amaranth.sim import *

from spi import SPI, SpiInit, IO

#
#

class MAX11125(SpiInit):

    ADC_CONFIG  = 0x10 << 11
    UNIPOLAR    = 0x11 << 11
    BIPOLAR     = 0x12 << 11
    RANGE       = 0x13 << 11
    SCAN_0      = 0x14 << 11
    SCAN_1      = 0x15 << 11
    SAMPLE      = 0x16 << 11

    def __init__(self, init=[], divider=1):
        SpiInit.__init__(self, width=16, init=init, divider=divider)

#
#

def sim():
    init = [
        0x0806,
        0x1000,
        0x9800,
        0x8800,
        0x9000,
    ]
    #init = []
    divider = 16
    m = MAX11125(init=init, divider=divider)
    sim = Simulator(m)

    do = IO(16)

    def tick(n=1):
        assert n
        for i in range(n):
            yield Tick()
            cs = yield m.cs
            sck = yield m.sck
            d = yield m.copi
            do.poll(cs, sck, d)

    def wait_ready():
        while True:
            yield from tick()
            r = yield m.ready
            if r:
                break

    def tx(data):
        yield m.start.eq(1)
        yield m.data.eq(data)
        yield from tick()
        yield m.start.eq(0)
        yield from tick()

    def proc():
        yield from tick(10)

        test = [
            0x0001,
            0x8000,
            0x1234,
            0xabcd,
            0xaaaa,
            0x5555,

            0x1111,
            0x2222,
            0x4444,
            0x8888,
            0x0,
            0xffff,
        ]

        for data in test:
            yield from wait_ready()
            yield from tick(divider)
            yield from tx(data)

        yield from wait_ready()

        yield from tick(5)

        assert do.rx == (init + test), [ hex(x) for x in do.rx ]

    sim.add_clock(1 / 32e6)
    sim.add_sync_process(proc)
    with sim.write_vcd("max11125.vcd", traces=m.ports()):
        sim.run()

#
#

if __name__ == "__main__":
    sim()

#   FIN
