v {xschem version=3.4.8 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {SKY130 STRONGARM LATCH} 40 10 0 0 0.65 0.65 {}
T {11-transistor core | 1.8 V | CLK low: reset | CLK high: evaluate} 40 60 0 0 0.32 0.32 {}
T {All L = 0.15 um; W in um. PMOS bodies: vdd; NMOS bodies: vss.} 40 95 0 0 0.28 0.28 {}
T {inp > inn: outp HIGH, outn LOW. Both outputs reset HIGH.} 40 130 0 0 0.28 0.28 {}
T {Cross-coupling uses the named outp / outn gate connections.} 40 165 0 0 0.28 0.28 {}
C {sky130_fd_pr/pfet_01v8.sym} 480 300 0 0 {name=MPN
W=4
L=0.15
nf=1 mult=1
ad="expr('int((@nf + 1)/2) * @W / @nf * 0.29')"
as="expr('int((@nf + 2)/2) * @W / @nf * 0.29')"
pd="expr('2*int((@nf + 1)/2) * (@W / @nf + 0.29)')"
ps="expr('2*int((@nf + 2)/2) * (@W / @nf + 0.29)')"
nrd="expr('0.29 / @W ')" nrs="expr('0.29 / @W ')"
sa=0 sb=0 sd=0
model=pfet_01v8 spiceprefix=X}
C {devices/lab_pin.sym} 500 300 0 0 {name=l1 lab=vdd hide=true}
C {sky130_fd_pr/pfet_01v8.sym} 920 300 0 1 {name=MPP
W=4
L=0.15
nf=1 mult=1
ad="expr('int((@nf + 1)/2) * @W / @nf * 0.29')"
as="expr('int((@nf + 2)/2) * @W / @nf * 0.29')"
pd="expr('2*int((@nf + 1)/2) * (@W / @nf + 0.29)')"
ps="expr('2*int((@nf + 2)/2) * (@W / @nf + 0.29)')"
nrd="expr('0.29 / @W ')" nrs="expr('0.29 / @W ')"
sa=0 sb=0 sd=0
model=pfet_01v8 spiceprefix=X}
C {devices/lab_pin.sym} 900 300 0 0 {name=l2 lab=vdd hide=true}
C {sky130_fd_pr/nfet_01v8.sym} 480 500 0 0 {name=MNN
W=4
L=0.15
nf=1 mult=1
ad="expr('int((@nf + 1)/2) * @W / @nf * 0.29')"
as="expr('int((@nf + 2)/2) * @W / @nf * 0.29')"
pd="expr('2*int((@nf + 1)/2) * (@W / @nf + 0.29)')"
ps="expr('2*int((@nf + 2)/2) * (@W / @nf + 0.29)')"
nrd="expr('0.29 / @W ')" nrs="expr('0.29 / @W ')"
sa=0 sb=0 sd=0
model=nfet_01v8 spiceprefix=X}
C {devices/lab_pin.sym} 500 500 0 0 {name=l3 lab=vss hide=true}
C {sky130_fd_pr/nfet_01v8.sym} 920 500 0 1 {name=MNP
W=4
L=0.15
nf=1 mult=1
ad="expr('int((@nf + 1)/2) * @W / @nf * 0.29')"
as="expr('int((@nf + 2)/2) * @W / @nf * 0.29')"
pd="expr('2*int((@nf + 1)/2) * (@W / @nf + 0.29)')"
ps="expr('2*int((@nf + 2)/2) * (@W / @nf + 0.29)')"
nrd="expr('0.29 / @W ')" nrs="expr('0.29 / @W ')"
sa=0 sb=0 sd=0
model=nfet_01v8 spiceprefix=X}
C {devices/lab_pin.sym} 900 500 0 0 {name=l4 lab=vss hide=true}
N 500 230 500 270 {lab=vdd}
C {devices/lab_pin.sym} 500 230 0 0 {name=l5 lab=vdd}
N 500 330 500 390 {lab=outn}
N 500 390 500 470 {lab=outn}
C {devices/lab_pin.sym} 500 390 0 0 {name=l6 lab=outn}
C {devices/lab_pin.sym} 460 300 0 0 {name=l7 lab=outp}
C {devices/lab_pin.sym} 460 500 0 0 {name=l8 lab=outp}
N 900 230 900 270 {lab=vdd}
C {devices/lab_pin.sym} 900 230 0 0 {name=l9 lab=vdd}
N 900 330 900 390 {lab=outp}
N 900 390 900 470 {lab=outp}
C {devices/lab_pin.sym} 900 390 0 1 {name=l10 lab=outp}
C {devices/lab_pin.sym} 940 300 0 1 {name=l11 lab=outn}
C {devices/lab_pin.sym} 940 500 0 1 {name=l12 lab=outn}
C {sky130_fd_pr/nfet_01v8.sym} 480 700 0 0 {name=MINP
W=8
L=0.15
nf=1 mult=1
ad="expr('int((@nf + 1)/2) * @W / @nf * 0.29')"
as="expr('int((@nf + 2)/2) * @W / @nf * 0.29')"
pd="expr('2*int((@nf + 1)/2) * (@W / @nf + 0.29)')"
ps="expr('2*int((@nf + 2)/2) * (@W / @nf + 0.29)')"
nrd="expr('0.29 / @W ')" nrs="expr('0.29 / @W ')"
sa=0 sb=0 sd=0
model=nfet_01v8 spiceprefix=X}
C {devices/lab_pin.sym} 500 700 0 0 {name=l13 lab=vss hide=true}
C {sky130_fd_pr/nfet_01v8.sym} 920 700 0 1 {name=MINN
W=8
L=0.15
nf=1 mult=1
ad="expr('int((@nf + 1)/2) * @W / @nf * 0.29')"
as="expr('int((@nf + 2)/2) * @W / @nf * 0.29')"
pd="expr('2*int((@nf + 1)/2) * (@W / @nf + 0.29)')"
ps="expr('2*int((@nf + 2)/2) * (@W / @nf + 0.29)')"
nrd="expr('0.29 / @W ')" nrs="expr('0.29 / @W ')"
sa=0 sb=0 sd=0
model=nfet_01v8 spiceprefix=X}
C {devices/lab_pin.sym} 900 700 0 0 {name=l14 lab=vss hide=true}
N 500 530 500 620 {lab=n_inp}
N 500 620 500 670 {lab=n_inp}
C {devices/lab_pin.sym} 500 620 0 0 {name=l15 lab=n_inp}
N 500 730 500 800 {lab=tail}
N 900 530 900 620 {lab=n_inn}
N 900 620 900 670 {lab=n_inn}
C {devices/lab_pin.sym} 900 620 0 1 {name=l16 lab=n_inn}
N 900 730 900 800 {lab=tail}
C {devices/lab_pin.sym} 460 700 0 0 {name=l17 lab=inp}
C {devices/lab_pin.sym} 940 700 0 1 {name=l18 lab=inn}
N 500 800 700 800 {lab=tail}
N 700 800 900 800 {lab=tail}
N 700 800 700 850 {lab=tail}
C {devices/lab_pin.sym} 700 800 0 0 {name=l19 lab=tail}
C {sky130_fd_pr/nfet_01v8.sym} 680 880 0 0 {name=MTAIL
W=2
L=0.15
nf=1 mult=1
ad="expr('int((@nf + 1)/2) * @W / @nf * 0.29')"
as="expr('int((@nf + 2)/2) * @W / @nf * 0.29')"
pd="expr('2*int((@nf + 1)/2) * (@W / @nf + 0.29)')"
ps="expr('2*int((@nf + 2)/2) * (@W / @nf + 0.29)')"
nrd="expr('0.29 / @W ')" nrs="expr('0.29 / @W ')"
sa=0 sb=0 sd=0
model=nfet_01v8 spiceprefix=X}
C {devices/lab_pin.sym} 700 880 0 0 {name=l20 lab=vss hide=true}
C {devices/lab_pin.sym} 660 880 0 0 {name=l21 lab=clk}
N 700 910 700 950 {lab=vss}
C {devices/lab_pin.sym} 700 950 0 0 {name=l22 lab=vss}
C {sky130_fd_pr/pfet_01v8.sym} 120 300 0 0 {name=MRON
W=1
L=0.15
nf=1 mult=1
ad="expr('int((@nf + 1)/2) * @W / @nf * 0.29')"
as="expr('int((@nf + 2)/2) * @W / @nf * 0.29')"
pd="expr('2*int((@nf + 1)/2) * (@W / @nf + 0.29)')"
ps="expr('2*int((@nf + 2)/2) * (@W / @nf + 0.29)')"
nrd="expr('0.29 / @W ')" nrs="expr('0.29 / @W ')"
sa=0 sb=0 sd=0
model=pfet_01v8 spiceprefix=X}
C {devices/lab_pin.sym} 140 300 0 0 {name=l23 lab=vdd hide=true}
N 140 230 140 270 {lab=vdd}
C {devices/lab_pin.sym} 140 230 0 0 {name=l24 lab=vdd}
C {devices/lab_pin.sym} 100 300 0 0 {name=l25 lab=clk}
N 140 330 140 390 {lab=outn}
N 140 390 500 390 {lab=outn}
C {sky130_fd_pr/pfet_01v8.sym} 1280 300 0 1 {name=MROP
W=1
L=0.15
nf=1 mult=1
ad="expr('int((@nf + 1)/2) * @W / @nf * 0.29')"
as="expr('int((@nf + 2)/2) * @W / @nf * 0.29')"
pd="expr('2*int((@nf + 1)/2) * (@W / @nf + 0.29)')"
ps="expr('2*int((@nf + 2)/2) * (@W / @nf + 0.29)')"
nrd="expr('0.29 / @W ')" nrs="expr('0.29 / @W ')"
sa=0 sb=0 sd=0
model=pfet_01v8 spiceprefix=X}
C {devices/lab_pin.sym} 1260 300 0 0 {name=l26 lab=vdd hide=true}
N 1260 230 1260 270 {lab=vdd}
C {devices/lab_pin.sym} 1260 230 0 1 {name=l27 lab=vdd}
C {devices/lab_pin.sym} 1300 300 0 1 {name=l28 lab=clk}
N 1260 330 1260 390 {lab=outp}
N 1260 390 900 390 {lab=outp}
C {sky130_fd_pr/pfet_01v8.sym} 300 590 0 0 {name=MRIP
W=1
L=0.15
nf=1 mult=1
ad="expr('int((@nf + 1)/2) * @W / @nf * 0.29')"
as="expr('int((@nf + 2)/2) * @W / @nf * 0.29')"
pd="expr('2*int((@nf + 1)/2) * (@W / @nf + 0.29)')"
ps="expr('2*int((@nf + 2)/2) * (@W / @nf + 0.29)')"
nrd="expr('0.29 / @W ')" nrs="expr('0.29 / @W ')"
sa=0 sb=0 sd=0
model=pfet_01v8 spiceprefix=X}
C {devices/lab_pin.sym} 320 590 0 0 {name=l29 lab=vdd hide=true}
N 320 520 320 560 {lab=vdd}
C {devices/lab_pin.sym} 320 520 0 0 {name=l30 lab=vdd}
C {devices/lab_pin.sym} 280 590 0 0 {name=l31 lab=clk}
N 320 620 500 620 {lab=n_inp}
C {sky130_fd_pr/pfet_01v8.sym} 1100 590 0 1 {name=MRIN
W=1
L=0.15
nf=1 mult=1
ad="expr('int((@nf + 1)/2) * @W / @nf * 0.29')"
as="expr('int((@nf + 2)/2) * @W / @nf * 0.29')"
pd="expr('2*int((@nf + 1)/2) * (@W / @nf + 0.29)')"
ps="expr('2*int((@nf + 2)/2) * (@W / @nf + 0.29)')"
nrd="expr('0.29 / @W ')" nrs="expr('0.29 / @W ')"
sa=0 sb=0 sd=0
model=pfet_01v8 spiceprefix=X}
C {devices/lab_pin.sym} 1080 590 0 0 {name=l32 lab=vdd hide=true}
N 1080 520 1080 560 {lab=vdd}
C {devices/lab_pin.sym} 1080 520 0 1 {name=l33 lab=vdd}
C {devices/lab_pin.sym} 1120 590 0 1 {name=l34 lab=clk}
N 1080 620 900 620 {lab=n_inn}
T {Output reset} 40 440 0 0 0.28 0.28 {}
T {Internal-node reset} 40 660 0 0 0.28 0.28 {}
T {Input differential pair} 600 760 0 0 0.25 0.25 {}
T {Clocked tail} 850 900 0 0 0.25 0.25 {}
T {SUBCIRCUIT PORTS} 40 1000 0 0 0.32 0.32 {}
C {devices/ipin.sym} 100 1060 0 0 {name=p1 lab=inp}
C {devices/ipin.sym} 270 1060 0 0 {name=p2 lab=inn}
C {devices/ipin.sym} 440 1060 0 0 {name=p3 lab=clk}
C {devices/opin.sym} 610 1060 0 0 {name=p4 lab=outp}
C {devices/opin.sym} 780 1060 0 0 {name=p5 lab=outn}
C {devices/iopin.sym} 950 1060 0 0 {name=p6 lab=vdd}
C {devices/iopin.sym} 1120 1060 0 0 {name=p7 lab=vss}
