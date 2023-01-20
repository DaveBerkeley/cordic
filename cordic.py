#!/bin/env python3

import math

from amaranth import *
from amaranth.sim import *

from amaranth.utils import bits_for

#
#   Core CORIDC Engine
#
#   handles signed binary representing -90 .. +90 degrees

class CordicCore(Elaboratable):

    # Gain from the atan() approximation
    K = 1.646760258121

    def __init__(self, a_width, o_width):

        self.a_width = a_width
        self.o_width = o_width

        # Initial state
        self.x0 = Signal(signed(o_width))
        self.y0 = Signal(signed(o_width))
        self.z0 = Signal(unsigned(a_width))

        self.start = Signal()
        self.ready = Signal(reset=1)

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
            m.d.sync += self.iteration.eq(self.iteration+1)

        with m.If(self.iteration == (self.iterations-1)):
            m.d.sync += self.ready.eq(1)

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
#   Cordic handling all 4 quadrants

class Cordic(Elaboratable):

    def __init__(self, a_width, o_width):
        self.core = CordicCore(a_width, o_width)

        self.X0 = int(0.99 * (1 << o_width) / (self.core.K * 2))        

        # Input signals
        self.x0 = Signal(signed(o_width))
        self.y0 = Signal(signed(o_width))
        self.z0 = Signal(unsigned(a_width))
        self.offset = Signal(signed(o_width))

        self.start = Signal()

        # Output Signals
        self.x = Signal(signed(o_width))
        self.y = Signal(signed(o_width))
        self.z = Signal(signed(a_width))

        self.ready = Signal()

        self.quadrant = Signal(2)

    def elaborate(self, platform):
        m = Module()

        m.submodules += self.core

        m.d.sync += [
            self.core.start.eq(self.start),
            self.ready.eq(self.core.ready),
        ]

        quad = self.z0 >> (self.core.a_width - 2) # top 2 bits of z0

        with m.If(self.start):
            m.d.sync += [
                self.quadrant.eq(quad),
                self.core.x0.eq(self.x0),
                self.core.y0.eq(self.y0),
                self.core.z0.eq(self.z0 << 1),
            ]

        with m.If(self.core.ready):
            # latch the outputs according to the quadrant
            with m.If((self.quadrant == 0) | (self.quadrant == 3)):
                m.d.sync += [
                    self.x.eq(self.offset + self.core.x),
                    self.y.eq(self.offset + self.core.y),
                    self.z.eq(self.core.z),
                ]
            with m.If((self.quadrant == 1) | (self.quadrant == 2)): 
                m.d.sync += [
                    self.x.eq(self.offset - self.core.x),
                    self.y.eq(self.offset - self.core.y),
                    self.z.eq(self.core.z),
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

def sim_core(m):
    sim = Simulator(m)

    def tick(n=1):
        assert n
        for i in range(n):
            yield Tick()

    a_range = 1 << m.a_width
    o_range = 1 << m.o_width
    x0 = int(0.99 * o_range / (m.K * 2))
    y0 = 0

    def run(x0, y0, z0):

        yield m.x0.eq(x0)
        yield m.y0.eq(y0)
        yield m.z0.eq(z0)

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

        for z0 in range(-(a_range-1)//2, a_range//2):
            x, y = yield from run(x0, y0, z0)
            print("cordic", z0, signed(x), signed(y))
            # TODO : better validation

            # ./cordic.py | grep cordic  > /tmp/a.csv
            # echo -e "set key off\nplot '/tmp/a.csv' u 2:3, '' u 2:4" | gnuplot --persist

    sim.add_clock(1 / 50e6)
    sim.add_sync_process(proc)
    with sim.write_vcd("cordic.vcd", traces=m.ports()):
        sim.run()

#
#

def sim_cordic(m):
    sim = Simulator(m)

    def tick(n=1):
        assert n
        for i in range(n):
            yield Tick()

    def wait_ready(state=True):
        while True:
            r = yield m.ready
            if r == state:
                break
            yield from tick()

    def run(x0, y0, z0, offset):
        yield from wait_ready()

        yield m.x0.eq(x0)
        yield m.y0.eq(y0)
        yield m.z0.eq(z0)
        yield m.offset.eq(offset)
        yield m.start.eq(1)
        yield from tick()
        yield m.start.eq(0)

        yield from wait_ready(False)
        yield from wait_ready(True)
        x = yield m.x
        y = yield m.y
        z = yield m.z
        return x, y, z

    def proc():
        yield from tick(2)

        mask = (1 << m.core.a_width) - 1

        x0 = m.X0
        offset = (1 << m.core.o_width) >> 1

        for a in range(0, 1 << m.core.a_width, 1):
            x, y, z = yield from run(x0, 0, a, offset)
            z0 = yield m.core.z0
            def fn(v):
                return hex(mask & v)
            print("quad", fn(a), fn(x), fn(y), fn(z), z0)

            # ./cordic.py | grep quad > /tmp/b.csv
            # echo -e "set key off\nplot '/tmp/b.csv' u 2:3, '' u 2:4" | gnuplot --persist

        yield from tick()

    sim.add_clock(1 / 50e6)
    sim.add_sync_process(proc)
    with sim.write_vcd("cordic2.vcd", traces=m.ports()):
        sim.run()

#
#

if __name__ == "__main__":

    a_width = 12
    o_width = 12
    dut = CordicCore(a_width=a_width, o_width=o_width)
    sim_core(dut)

    dut = Cordic(a_width=a_width, o_width=o_width)
    sim_cordic(dut)

# FIN
