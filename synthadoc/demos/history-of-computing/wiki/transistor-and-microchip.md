---
aliases: []
confidence: high
created: 2026-04-09
lint_warnings:
- claim: Bardeen, Brattain, and Shockley shared the 1956 Nobel Prize in Physics for
 the discovery.
 concern: The Nobel Prize was awarded for 'their researches on semiconductors and
 their discovery of the transistor effect,' not simply 'the discovery' of the transistor.
- claim: The 4004 ... could address 640 bytes of program memory.
 concern: The 4004 used a 12-bit address space for program ROM, allowing it to address
 up to 4,096 bytes of program memory, not 640 bytes. The 640-byte figure is more
 commonly associated with the IBM PC's conventional memory limit.
orphan: false
sources:
- file: public-domain/riordan-hoddeson-crystal-fire.txt
 hash: placeholder
 ingested: 2026-04-09
 size: 0
- file: C:\Users\ladmin\wikis\history-of-computing\raw_sources\public-domain\riordan-hoddeson-crystal-fire.txt
 hash: ae44ed9a15e09cc141907f56d2cdda05797749f6a34b6375ba82d05384c85358
 ingested: '2026-07-12'
 size: 7170
status: active
tags:
- hardware
- transistor
- integrated-circuit
- moores-law
title: Transistor and Microchip
type: technology
updated: '2026-07-12'
---

# Transistor and Microchip

The transistor and the integrated circuit are the twin inventions that made modern computing physically possible. Without them, [[von-neumann-architecture]] computers would remain room-sized vacuum-tube machines consuming megawatts of power.

## The Transistor (1947)

John Bardeen, Walter Brattain, and William Shockley at Bell Labs demonstrated the first point-contact transistor on 16 December 1947. The transistor is a semiconductor device that amplifies or switches electrical signals. Unlike vacuum tubes, transistors are small, reliable, consume little power, and generate minimal heat. Bardeen, Brattain, and Shockley shared the 1956 Nobel Prize in Physics for the discovery.

## The Integrated Circuit (1958–1959)

Jack Kilby at Texas Instruments (1958) and Robert Noyce at Fairchild Semiconductor (1959) independently invented the integrated circuit — multiple transistors and their connections fabricated on a single piece of semiconductor. Kilby won the Nobel Prize in Physics in 2000; Noyce had died in 1990. The IC eliminated the "tyranny of numbers": hand-soldering thousands of discrete transistors was slow, expensive, and unreliable.

## Intel 4004 and the Microprocessor (1971)

Intel's 4004, designed by Federico Faggin, Ted Hoff, and Stanley Mazor, placed a complete CPU on a single chip for the first time. The 4004 contained 2,300 transistors and ran at 740 kHz. It was designed for a Japanese calculator company, but Intel recognised it as a general-purpose computing engine. The microprocessor made the [[personal-computer-revolution]] economically viable.

## Moore's Law

Gordon Moore, Intel co-founder, observed in 1965 that the number of transistors on a chip doubled roughly every two years at constant cost. This empirical trend held for over 50 years, driving exponential improvements in computing power and reductions in cost. Modern chips contain tens of billions of transistors at nanometre scales.

## Physical Limits

By the 2010s, transistors approached atomic dimensions. Classical scaling slowed, prompting the industry to pursue 3D chip stacking, chiplets, and specialised processors (GPUs, TPUs, NPUs) to continue performance improvements. The end of Moore's Law has accelerated interest in quantum computing and neuromorphic architectures.

See also: [[von-neumann-architecture]] for the logical design these chips implement; [[programming-languages-overview]] for the software abstraction layers above the hardware.

## The Microprocessor (1971)

The microprocessor brought the entire [[von-neumann-architecture]] central processing unit of a computer onto a single chip. Intel's 4004, designed by Federico Faggin, Ted Hoff, and Stanley Mazor, was fabricated in Intel's silicon gate MOS process and contained 2,300 transistors on a chip roughly 3mm by 4mm. It operated at 740 kHz, processed 4 bits at a time, and could address 640 bytes of program memory. ^[riordan-hoddeson-crystal-fire.txt:45-45]

The 4004's existence as a general-purpose CPU on a chip made the [[personal-computer-revolution]] economically feasible. Subsequent Intel processors — the 8080 (1974), the 8086 (1978), and their descendants — powered the Altair, the IBM PC, and the industry of compatible machines that followed. ^[riordan-hoddeson-crystal-fire.txt:47-47]

## Physical Limits and the End of Scaling

By the 2010s, transistors in leading-edge processors had gate lengths of a few nanometres — approaching atomic dimensions. Fundamental physical limits began to constrain continued scaling: quantum tunnelling caused leakage current at extremely small dimensions, and heat dissipation became a critical constraint. The simple scaling that had characterised Moore's Law began to slow. ^[riordan-hoddeson-crystal-fire.txt:51-51]

The industry responded by moving from two-dimensional planar transistors to three-dimensional FinFET structures, and by stacking multiple chips vertically in packages. Specialised processors — GPUs for parallel computation, TPUs for machine learning inference, NPUs for neural network acceleration — complemented general-purpose CPUs. These developments continued the practical trajectory of Moore's Law even as classical transistor scaling reached its limits. ^[riordan-hoddeson-crystal-fire.txt:53-53]

## Vacuum Tubes and Their Limitations

Before the transistor, electronic amplifiers and switches used vacuum tubes — glass envelopes evacuated of air, containing electrodes through which current flowed. Vacuum tubes performed reliably for radio and early computing but had significant drawbacks: they were large, generated considerable heat, consumed substantial power, and failed frequently. The [[eniac|ENIAC]] computer, completed in 1945, contained 17,468 vacuum tubes and required a dedicated staff simply to replace the tubes that failed during operation. Bell Labs, aware of the commercial importance of solid-state amplifiers for telephone networks, assembled a research team specifically to pursue the problem. ^[riordan-hoddeson-crystal-fire.txt:7-9]

## The Bell Labs Team and the December 1947 Demonstration

The Bell Labs solid-state physics group was led by [[william-shockley|William Shockley]], with [[john-bardeen|John Bardeen]] carrying out the theoretical analysis and [[walter-brattain|Walter Brattain]] the experimental work. On 16 December 1947, Bardeen and Brattain demonstrated the first working point-contact transistor at Murray Hill, New Jersey. Bell Labs management arranged an internal demonstration on 23 December 1947 and withheld the announcement for several months while filing patents; the public announcement came in June 1948. ^[riordan-hoddeson-crystal-fire.txt:13-17]

## The Junction Transistor and the Shift to Silicon

Disappointed at being excluded from the experimental breakthrough, Shockley independently developed the junction transistor — a superior sandwiched-layer design that was more reliable and easier to manufacture than the point-contact device. Germanium was the initial semiconductor of choice, but silicon offered advantages: greater abundance, higher operating temperature tolerance, and a stable oxide layer that proved critical for later integrated circuit manufacture. Gordon Teal at Texas Instruments grew the first silicon transistors in 1954, and silicon rapidly displaced germanium for most applications. ^[riordan-hoddeson-crystal-fire.txt:23-25]

## The Kilby–Noyce Integrated Circuit (1958–1959)

Through the 1950s, electronic systems were assembled by hand-wiring discrete components — the so-called "tyranny of numbers" meant reliability fell as connections multiplied. Jack Kilby at Texas Instruments proposed in the summer of 1958 that all components of an electronic circuit could be fabricated from a single piece of semiconductor material, and demonstrated a working integrated circuit in September 1958. Independently, [[robert-noyce|Robert Noyce]] at Fairchild Semiconductor developed a more manufacturable planar-process approach, depositing components on a flat silicon surface through photolithographic masking steps and connecting them with metal traces rather than fine wires. Kilby received the Nobel Prize in Physics in 2000; Noyce had died in 1990. ^[riordan-hoddeson-crystal-fire.txt:29-35]

## Moore's Law

In 1965, Gordon Moore, then research director at Fairchild Semiconductor, observed in *Electronics* magazine that the number of components per integrated circuit had roughly doubled every year since the first ICs were manufactured. He projected the trend would continue for at least a decade and predicted that by 1975 it would be feasible to put 65,000 components on a single chip. Moore revised his estimate to a doubling approximately every two years in 1975. The empirical trend held for over fifty years, driving down the price of computing hardware continuously as transistor density increased. ^[riordan-hoddeson-crystal-fire.txt:39-41]

## Physical Limits and the End of Classical Scaling

By the 2010s, transistors in leading-edge processors had gate lengths of only a few nanometres — approaching atomic dimensions. Quantum tunnelling caused leakage current at these scales, and heat dissipation became a critical constraint. The industry responded by moving from planar transistors to three-dimensional FinFET structures, by stacking multiple chips vertically in packages, and by deploying specialised processors — GPUs, TPUs, and NPUs — alongside general-purpose CPUs. These adaptations continued the practical trajectory of Moore's Law even as classical transistor scaling reached its physical limits. ^[riordan-hoddeson-crystal-fire.txt:51-53]