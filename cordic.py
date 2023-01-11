#!/bin/env python3

import math

from enum import IntEnum, unique

from amaranth import *
from amaranth.sim import *

from amaranth.utils import bits_for

#
#   Fixed point values of 'width' bits
#   representing numbers in the range +1.9999 to -1.9999

class Num:

    def __init__(self, width):
        assert width >= 2
        self.width = width
        self.gain = 1 << (width-2)

    def f_to_s(self, f):
        "float to signal"
        assert -2.0 < f < 2.0

        sign = 0
        if f < 0.0:
            sign = 1 << (self.width-1)
            f = -f
        f *= self.gain
        f += sign
        return int(f)

    def s_to_f(self, s):
        "signal to float"
        sign = 1
        if s & (1 << (self.width-1)):
            sign = -1
            s &= ~(1 << self.width-1)

        f = float(s) / self.gain
        return f * sign

    def approx(self, f1, f2):
        err = abs(f1 - f2)
        margin = 1.0 / self.gain
        return err < margin

f_test = (
    ( 12, 1.9999, 0x7ff ),
    ( 4, 1.9999, 0x7 ),
    ( 4, -1.9999, 0xf ),
    ( 12, 1.75, 0x700 ),
    ( 12, 0.75, 0x300 ),
    ( 12, 0.25, 0x100 ),
    ( 12, 0.0, 0x0 ),
    ( 12, -0.25, 0x900 ),
    ( 12, -0.5, 0xa00 ),
    ( 12, -0.9999, 0xbff ),
    ( 12, -1.9999, 0xfff ),
)

for width, f, x in f_test:
    n = Num(width)
    assert n.f_to_s(f) == x, (width, f, hex(x), hex(n.f_to_s(f)))
    assert n.approx(n.s_to_f(n.f_to_s(f)), f), (n.f_to_s(f), n.s_to_f(n.f_to_s(f)), f)

#
#

class Cordic(Elaboratable):

    # Gain from the atan() approximation
    K = 1.646760258121

    def __init__(self, width=16):

        self.width = width

        # Initial state
        self.x0 = Signal(signed(width))
        self.y0 = Signal(signed(width))
        self.z0 = Signal(signed(width))

        self.start = Signal()
        self.ready = Signal()
 
        self.x = Signal(signed(width))
        self.y = Signal(signed(width))
        self.z = Signal(signed(width))

        # ROM for atan(pow(2,-i)) values
        self.rom = self.make_rom()
        self.iterations = len(self.rom)
        # ROM output for this iteration
        self.a = Signal(signed(width))

        # bit-shifted versions
        self.ys = Signal(signed(width))
        self.xs = Signal(signed(width))

        self.iteration = Signal(bits_for(self.iterations))
        self.d = Signal()


    def make_rom(self):
        rom = []
        n = Num(self.width)
        i = 0;
        while True:
            s = math.atan(1.0 / (1 << i))
            s = n.f_to_s(s)
            rom.append(Const(s))
            if s == 0:
                break
            i += 1
        return Array(rom)

    def elaborate(self, platform):
        m = Module()

        m.d.comb += [
            # sign of the z register
            self.d.eq(self.z[self.width-1] == 0),
            # atan(pow(2, -i)) value for this iteration
            self.a.eq(self.rom[self.iteration]),

            # shifted feedback
            self.xs.eq(self.x >> self.iteration),
            self.ys.eq(self.y >> self.iteration),
        ]

        with m.If(self.ready == 0):
            m.d.sync += [
                self.iteration.eq(self.iteration+1),
            ]
        with m.If(self.iteration == (self.iterations-1)):
            m.d.sync += [
                self.ready.eq(1),
            ]

        with m.If(self.start):
            m.d.sync += [
                self.x.eq(self.x0),
                self.y.eq(self.y0),
                self.z.eq(self.z0),
                self.iteration.eq(0),
                self.ready.eq(0),
            ]
        with m.Elif(self.ready == 0):
            with m.If(self.d):
                m.d.sync += [
                    self.z.eq(self.z - self.a),
                    self.x.eq(self.x - self.ys),
                    self.y.eq(self.y + self.xs),
                ]
            with m.Else():
                m.d.sync += [
                    self.z.eq(self.z + self.a),
                    self.x.eq(self.x + self.ys),
                    self.y.eq(self.y - self.xs),
                ]

        return m

    def ports(self):
        return [
            self.x0, self.y0, self.z0, 
            self.x, self.y, self.z, 
            self.start,
            self.ready,
        ]

#
#

def sim(m):
    #print('run simulation')
    sim = Simulator(m)

    def tick(n=1):
        assert n
        for i in range(n):
            yield Tick()

    def to_s(f):
        n = Num(m.width)
        return n.f_to_s(f)

    def run(angle):

        yield m.x0.eq(to_s(1.0/m.K))
        yield m.y0.eq(0)
        a = math.radians(angle)
        yield m.z0.eq(to_s(a))

        yield m.start.eq(1)
        yield from tick(1)
        yield m.start.eq(0)

        while True:
            yield from tick()
            s = yield m.ready
            x = yield m.x
            y = yield m.y
            if s:
                break

        return x, y

    def proc():
        n = Num(m.width)
        for angle in range(90):
            x, y = yield from run(angle)
            r = math.radians(angle)
            sin = math.sin(r)
            cos = math.cos(r)
            xf = n.s_to_f(x)
            yf = n.s_to_f(y)
            print(angle, hex(n.f_to_s(r)), hex(x), hex(y), xf, yf, cos, sin)
            nn = Num(m.width - 1)
            err = abs(xf - cos)
            assert 0, err
            assert nn.approx(xf, cos), (xf, cos, nn.approx(xf, cos))

    sim.add_clock(1 / 50e6)
    sim.add_sync_process(proc)
    with sim.write_vcd("cordic.vcd", traces=m.ports()):
        sim.run()

#
#

if __name__ == "__main__":

    width = 12
    dut = Cordic(width=width)
    sim(dut)

# FIN
