FPGA CORDIC Engine
=============

Implementation of 
[CORDIC](https://en.wikibooks.org/w/index.php?title=Digital_Circuits/CORDIC)
in 
[Amaranth](https://github.com/amaranth-lang/amaranth).

CORDIC (for "COordinate Rotation DIgital Computer") is a method of deriving sin() and cos() from an angle. It was first described by Jack E. Volder(1) in his 1959 paper "The CORDIC Trigonometric Computing Technique".

It uses an iterative technique of successive approximation to generate sin and cos outputs. A binary search through different rotations is accumulated until the desired angle is acheived.

The core of the engine is described by the following block diagram :

![hello](CORDIC.png)

The initial x0, y0 and z0 values are loaded in. x0 and y0 are the initial sin & cos values. z0 is the desired phase angle in radians. The engine is clocked for a number of iterations, the x and y outputs are the cos and sin of the desired angle.

The table of incremental rotations are shown here as **α**n. These are stored as an Array of constants, indexed by the iteration number. The number of iterations is determined by the **α** table. When the value becomes 0, no further adjustment is possible, so you can stop iterating. The number of iterations is therefore determined by the bit-width, which can be specified.

The algorithm has a gain of K, so if x0 is loaded with 1.0/K and y0 with 0.0, the output will be scaled to unity gain.

The unit can calculate sin/cos in the first and fourth quadrants (-90 .. +90 degrees).

4 quadrant operation is acheived by modifying the inputs and outputs of the core unit. You can also add a DC offset to the output to convert the signed output to unsigned, eg for sending to a DAC.

There are two modes of operation - rotation mode, which is used to generate sin/cos outputs from theta input, and vector mode, which takes a sin/cos pair as input and generates theta and amplitude as output. The two modes can be selected by the state of the 'vector_mode' input signal.

----

1. Volder, Jack E. (1959-03-03). "The CORDIC Computing Technique"
