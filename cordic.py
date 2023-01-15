#!/bin/env python3

import math

from amaranth import *
from amaranth.sim import *

from amaranth.utils import bits_for

#
#

class Cordic(Elaboratable):

    # Gain from the atan() approximation
    K = 1.646760258121

    def __init__(self, a_width, o_width):

        self.a_width = a_width
        self.o_width = o_width

        # Initial state
        self.x0 = Signal(signed(o_width))
        self.y0 = Signal(signed(o_width))
        self.z0 = Signal(signed(a_width))

        self.start = Signal()
        self.ready = Signal()
 
        self.x = Signal(signed(o_width))
        self.y = Signal(signed(o_width))
        self.z = Signal(signed(a_width))

        # ROM for atan(pow(2,-i)) values
        self.rom = self.make_rom()
        self.iterations = len(self.rom)
        # ROM output for this iteration
        self.a = Signal(signed(a_width))

        # bit-shifted versions
        self.ys = Signal(signed(o_width))
        self.xs = Signal(signed(o_width))

        self.iteration = Signal(bits_for(self.iterations))
        self.d = Signal()

    def make_rom(self):
        rom = []
        scale = (1 << self.a_width) / math.pi
        i = 0;
        while True:
            f = math.atan(1.0 / (1 << i))
            s = int(f * scale)
            #print("rom", s)
            rom.append(Const(s))
            if s == 0:
                break
            i += 1
        return Array(rom)

    def elaborate(self, platform):
        m = Module()

        m.d.comb += [
            # sign of the z register
            self.d.eq(self.z[self.a_width-1] == 0),
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

def sim_cordic(m):
    sim = Simulator(m)

    def tick(n=1):
        assert n
        for i in range(n):
            yield Tick()

    a_range = 1 << m.a_width
    o_range = 1 << m.o_width
    x0 = int(0.99 * o_range / (m.K * 2))

    def run(angle, x0):

        yield m.x0.eq(x0)
        yield m.y0.eq(0)
        yield m.z0.eq(angle)

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

        def signed(x):
            sign = 1 << (m.o_width - 1)
            mask = sign - 1
            if x & sign:
                return (x & mask) - sign
            return x & mask

        for angle in range(-(a_range-1)//2, a_range//2):
            x, y = yield from run(angle, x0)
            print("cordic", angle, signed(x), signed(y))
            # TODO : better validation

    sim.add_clock(1 / 50e6)
    sim.add_sync_process(proc)
    with sim.write_vcd("cordic.vcd", traces=m.ports()):
        sim.run()

#
#

if __name__ == "__main__":

    a_width = 8
    o_width = 12
    dut = Cordic(a_width=a_width, o_width=o_width)
    sim_cordic(dut)

# FIN
