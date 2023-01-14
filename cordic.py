#!/bin/env python3

import math

from amaranth import *
from amaranth.sim import *

from amaranth.utils import bits_for

#
#   Fixed point representation of a range of floats

class Num:

    def __init__(self, _range, fmax):
        self.mul = _range / (2.0 * fmax)

    def f_to_s(self, f):
        return int(f * self.mul)

    def s_to_f(self, s):
        return float(s / self.mul)

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
        n = Num(1 << self.width, math.pi/2.0)
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

class ToRadians(Elaboratable):

    def __init__(self, inwidth, outwidth):
        assert inwidth > 2, inwidth
        self.inwidth = inwidth
        self.outwidth = outwidth

        # input
        self.angle = Signal(unsigned(inwidth))
        # output 
        self.quadrant = Signal(2)
        self.radians = Signal(signed(outwidth))

        # 0..90 part of the angle 
        self.theta = Signal(unsigned(outwidth))

        # Factor to convert the 0..90 part of the angle to 0 .. pi/2 radians
        n = Num(outwidth)
        gain = math.pi / 2.0
        k = n.f_to_s(gain)
        self.r = Const(k)

    def elaborate(self, platform):
        m = Module()

        # theta is the 0..x angle representing 0..90
        # it needs to be expressed in outwidth,
        # so needs to be aligned correctly

        a = self.inwidth - 2
        b = self.outwidth
        c = abs(a - b)

        with m.If(a == b):
            m.d.comb += self.theta.eq(self.angle)
        with m.Elif(a < b):
            m.d.comb += self.theta.eq(self.angle << c)
        with m.Elif(a > b):
            m.d.comb += self.theta.eq(self.angle >> c)

        m.d.sync += [
            # top 2 bits of the angle
            self.quadrant.eq(self.angle >> (self.inwidth - 2)),
            # Multiplier
            self.radians.eq((self.r * self.theta) >> self.outwidth),
        ]

        return m

    def ports(self):
        return [ self.angle, self.quadrant, self.radians, ]


#
#

class SinCos(Elaboratable):

    def __init__(self, inwidth, outwidth):
        assert inwidth > 2, inwidth
        self.inwidth = inwidth
        self.outwidth = outwidth

        self.cordic = Cordic(width=outwidth)
        self.radians = ToRadians(inwidth, outwidth)

        # input data
        self.angle = Signal(inwidth)
        self.offset = Signal(unsigned(outwidth))

        # output data
        self.sin = Signal(signed(outwidth))
        self.cos = Signal(signed(outwidth))

        # Control signals
        self.start = Signal()
        self.ready = Signal()

        # delay through the ToRadians() module
        self.start_0 = Signal()

        # Compensate for the CORDIC gain K
        n = Num(outwidth)
        self.x0 = Const(n.f_to_s(2.0 / self.cordic.K))

    def elaborate(self, platform):
        m = Module()
        m.submodules += self.cordic
        m.submodules += self.radians

        # Connect the radians module
        m.d.comb += [
            self.radians.angle.eq(self.angle),
        ]

        m.d.comb += [
            # connect the CORDIC inputs
            self.cordic.x0.eq(self.x0),
            self.cordic.y0.eq(0),
            self.cordic.z0.eq(self.radians.radians),
        ]

        m.d.sync += [
            self.start_0.eq(self.start),
            self.cordic.start.eq(self.start_0),
            self.ready.eq(self.cordic.ready),
        ]

        quadrant = self.radians.quadrant

        with m.If(self.cordic.ready):

            # correct the output for each quadrant

            with m.If(quadrant == 0):
                m.d.sync += [
                    self.cos.eq(self.offset + self.cordic.x),
                    self.sin.eq(self.offset + self.cordic.y),
                ]
            with m.Elif(quadrant == 1):
                m.d.sync += [
                    self.cos.eq(self.offset - self.cordic.y),
                    self.sin.eq(self.offset + self.cordic.x),
                ]
            with m.Elif(quadrant == 2):
                m.d.sync += [
                    self.cos.eq(self.offset - self.cordic.x),
                    self.sin.eq(self.offset - self.cordic.y),
                ]
            with m.Elif(quadrant == 3):
                m.d.sync += [
                    self.cos.eq(self.offset + self.cordic.y),
                    self.sin.eq(self.offset - self.cordic.x),
                ]

        return m

    def ports(self):
        return [
            self.start, self.ready,
            self.angle,
            self.sin, self.cos,
        ] + self.cordic.ports()

#
#

def sim_cordic(m):
    sim = Simulator(m)

    def tick(n=1):
        assert n
        for i in range(n):
            yield Tick()

    nrange = 1 << m.width
    na = Num(nrange, 90.0)
    nx = Num(nrange, 1.0)

    def run(angle):

        yield m.x0.eq(nx.f_to_s(1.0/m.K))
        yield m.y0.eq(0)
        yield m.z0.eq(na.f_to_s(angle))

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
        mask = (1 << (m.width - 1)) - 1
        for angle in range(90):
            x, y = yield from run(angle)
            r = math.radians(angle)
            sin = math.sin(r)
            cos = math.cos(r)
            xf = nx.s_to_f(x)
            yf = nx.s_to_f(y)
            print("cordic", angle, hex(x & mask), hex(y & mask), xf, yf, cos, sin)
            # TODO : better validation

    sim.add_clock(1 / 50e6)
    sim.add_sync_process(proc)
    with sim.write_vcd("cordic.vcd", traces=m.ports()):
        sim.run()

#
#

def sim_radians(m):
    sim = Simulator(m)

    def tick(n=1):
        assert n
        for i in range(n):
            yield Tick()

    def proc():

        n = Num(m.outwidth)
        yield from tick(1)

        for i in range(1 << m.inwidth):
            yield m.angle.eq(i)
            yield from tick()
            t = yield m.theta
            yield from tick()
            q = yield m.quadrant
            r = yield m.radians
            #print(hex(i), q, hex(t), hex(r))

            # theta is angle without the top 2 bits
            mask = (1 << (m.inwidth - 2)) - 1
            tx = i & mask
            a, b, = (m.inwidth - 2), m.outwidth
            c = abs(a - b)
            if a < b:
                tx <<= c
            if a > b:
                tx >>= c
            assert t == tx, (i, t, tx, hex(mask))
            # top 2 bits
            qx = (i >> (m.inwidth - 2)) & 0x03
            assert q == qx, (i, q, qx)
            pi2 = n.f_to_s(math.pi / 2.0)
            rx = (pi2 * t) >> m.outwidth
            assert r == rx, (i, r, rx)

    sim.add_clock(1 / 50e6)
    sim.add_sync_process(proc)
    with sim.write_vcd("radians.vcd", traces=m.ports()):
        sim.run()

#
#

def sim_sincos(m):
    sim = Simulator(m)

    def tick(n=1):
        assert n
        for i in range(n):
            yield Tick()

    def proc():
        yield from tick(2)

        def fn(x):
            mask = (1 << m.outwidth) - 1
            return x & mask

        mid = (1 << (m.outwidth - 1)) - 1
        yield m.offset.eq(mid)

        for i in range(1 << m.inwidth):
            yield from tick(1)
            yield m.angle.eq(i)
            yield m.start.eq(1)
            yield from tick(1)
            yield m.start.eq(0)

            while True:
                r = yield m.ready
                if not r:
                    break
                yield from tick()

            while True:
                yield from tick()
                r = yield m.ready
                if r:
                    break

            s = yield fn(m.sin)
            c = yield fn(m.cos)
            r = yield m.radians.radians
            print("sincos", i, hex(c), hex(s), hex(r))

    sim.add_clock(1 / 50e6)
    sim.add_sync_process(proc)
    with sim.write_vcd("sincos.vcd", traces=m.ports()):
        sim.run()

#
#

if __name__ == "__main__":

    width = 12
    dut = Cordic(width=width)
    sim_cordic(dut)

    #dut = ToRadians(inwidth=10, outwidth=16)
    #sim_radians(dut)

    #dut = SinCos(inwidth=8, outwidth=width)
    #sim_sincos(dut)

# FIN
