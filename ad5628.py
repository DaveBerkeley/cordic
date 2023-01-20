#!/bin/env python3

from amaranth import *
from amaranth.sim import *

#
#   Driver for SPI 12-bit 8-channel DAC
#
#   https://digilent.com/reference/_media/pmod:pmod:pmodDA4_RM.pdf
#

class DAC(Elaboratable):

    C_REF = 0x8
    C_CONVERT = 0x3
    C_RESET = 0x7

    def __init__(self):
        # Outputs
        self.cs = Signal()
        self.copi = Signal()
        self.sck = Signal(reset=1)

        self.data = Signal(12)
        self.addr = Signal(4)
        self.cmd = Signal(4)
        self.start = Signal()

        self.ready = Signal(reset=1)

        # SPI interface
        self.sr = Signal(32)
        self.bit = Signal(range(32))

    def elaborate(self, platform):
        m = Module()

        m.d.comb += self.copi.eq(self.sr[31])

        # pad the 32-bit word with unused sections
        top = Const(0xf, 4)
        tail = Const(0xff, 8)

        m.d.sync += self.sck.eq(1)

        with m.If(self.ready):
            # end cs period
            m.d.sync += self.cs.eq(0)

        with m.If(self.start):
            # begin transfer
            m.d.sync += [
                self.bit.eq(31),
                self.ready.eq(0),

                self.cs.eq(1),
                self.sr.eq(Cat(tail, self.data, self.addr, self.cmd, top)),
            ]

        with m.If(self.cs):
            # running
            with m.If(~self.ready):
                m.d.sync += self.sck.eq(~self.sck)

            with m.If(~self.sck):
                m.d.sync += [
                    self.sr.eq(self.sr << 1),
                    self.bit.eq(self.bit - 1),
                ]

                with m.If(self.bit == 0):
                    # done
                    m.d.sync += self.ready.eq(1)

        return m

    def ports(self):
        return [
            self.cs, self.copi, self.sck,
            self.data, self.addr, self.cmd,
            self.start, self.ready,
        ]

#
#

def sim(m):
    sim = Simulator(m)

    state = {
        'ck' : 0,
        'cs' : 0,
        'sr' : [],
        'bit' : 0,
        'rx' : [],
    }

    def reset():
        # start of word
        state['bit'] = 0
        state['sr'] = []
        state['ck'] = 0

    def tick(n=1):
        assert n
        for i in range(n):
            yield Tick()

            # Rx SPI data
            cs = yield m.cs
            ck = yield m.sck
            d = yield m.copi
            if cs != state['cs']:
                if cs:
                    # start of word
                    reset()
                else:
                    # end of word
                    data = 0
                    for i in range(32):
                        data <<= 1
                        if state['sr'][i]:
                            data |= 1
                    state['rx'].append(data)
                    reset()
            state['cs'] = cs

            if cs and (ck != state['ck']):
                # -ve edge of clock
                if not ck:
                    state['bit'] += 1
                    state['sr'].append(d)
            state['ck'] = ck

    def wait_ready():
        while True:
            yield from tick()
            r = yield m.ready
            if r:
                break

    def tx(data, addr, cmd):
        yield from wait_ready()
        yield from tick()
        yield m.start.eq(1)
        yield m.data.eq(data)
        yield m.addr.eq(addr)
        yield m.cmd.eq(cmd)
        yield from tick()
        yield m.start.eq(0)

        yield from tick()

    def proc():
        yield from tick(5)

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

        for i, d in enumerate(test):
            assert state['rx'][i] == d, (i, state, hex(state['rx'][i]), hex(d))

        yield from tick(5)

    sim.add_clock(1 / 100e6)
    sim.add_sync_process(proc)
    with sim.write_vcd("ad5628.vcd", traces=m.ports()):
        sim.run()

#
#

if __name__ == "__main__":
    dut = DAC()
    sim(dut)

# FIN
