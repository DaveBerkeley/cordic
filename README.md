CORDIC Engine
=============

Implementation of 
[CORDIC](https://en.wikibooks.org/w/index.php?title=Digital_Circuits/CORDIC)
in 
[Amaranth](https://github.com/amaranth-lang/amaranth).

CORDIC (for "coordinate rotation digital computer") is a method of deriving sin() and cos() from an angle. It was first described by Jack E. Volder(1) in his 1959 paper "The CORDIC Trigonometric Computing Technique".

It uses an iterative technique of successive approximation to generate sin and cos outputs. A binary search through different rotations is accumulated until the desired angle is acheived.

The core of the engine is described by the following block diagram :

![hello](CORDIC.png)

The initial x0, y0 and z0 values are loaded in. x0 and y0 are the initial sin & cos values. z0 is the desired phase angle in radians. The engine is clocked for a number of iterations, the x and y outputs are the cos and sin of the desired angle.

The table of incremental rotations are shown here as _α_. These are stored as an Array ofconstants, indexed by the iteration number.

The algorithm has a gain of K, so if x0 is loaded with 1.0/K and y0 with 0.0, the output will be scaled to unity gain. The number representation is signed fixed point integer. The bit-width of the engine can be specified. The numbers +1.999 to -1.999 can be represented internally.

The unit can calculate sin/cos in the first quadrant (0 .. 90 degrees).

1. Volder, Jack E. (1959-03-03). "The CORDIC Computing Technique"
