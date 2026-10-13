# INP2RAD source reuse

Source: OpenCourant/Tools, commit beaf8a17c880242bb7ad43325a20bd589dc0f533,
input_converters/inp2rad/inp2rad/inp2rad.py. The MIT copyright/permission notice
is preserved in the source. The only local source patch makes tkinter optional.
CAELab's owned child selects the noninteractive entry and checks its Boolean
return and new output files. It does not call the upstream CLI pause.

The adapter admits a bounded flattened subset before conversion, retains the
original and converted decks, and replaces the converter's implicit time/mass
scaling defaults with explicit saved controls. This is not general Abaqus
compatibility. Shipped native converter binary hashes do not establish this
Python converter's source identity, or vice versa.
