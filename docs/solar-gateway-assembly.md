# Solar Power Assembly: LoRaWAN Gateway (Milesight UG67)

Instructions for assembling the solar power system that runs the UG67 gateway for the field water-temperature sensor network. Assemble and test everything on a bench first, then move it to the field.

## System overview

```
Solar panel (100 W)
   |  10 ft 10 AWG adaptor kit (MC4 to bare wire), 10 A fuse on positive
   v
Rover Li 20A MPPT controller  <--  BT-2 Bluetooth module (Renogy app)
   |  BATTERY terminals, 20-30 A fuse at battery positive
   v
Reserve Mini 12V 100Ah LiFePO4 (self-heating)

Rover LOAD terminals
   |  5 A fuse on positive
   v
Voltage stabilizer (8-40 V in, 12 V 3 A out)
   |
   v
UG67 M12 DC power cable  -->  UG67 gateway
```

Gateway draw is about 3.6 W typical (4.8 W max), roughly 90 Wh per day. The 100 Ah battery provides about 10 days of reserve with no sun.

## Parts

### Purchased

| Item | Purpose |
|---|---|
| Renogy 100W Lightweight Flexible Solar Panel | Power generation |
| Renogy Solar Panel Flat Roof Tilt Mount | Angles the panel toward the sun |
| Renogy Solar Panel to Charge Controller Adaptor Kit (10 ft, 10 AWG) | Panel to controller wiring |
| Renogy Rover Li 20A MPPT Charge Controller with BT-2 | Charges battery, powers the gateway |
| Renogy Reserve Mini Smart 12V 100Ah LiFePO4 (self-heating, Bluetooth) | Energy storage |
| Waterproof Voltage Stabilizer, DC 8-40 V to 12 V 3 A | Keeps gateway input within its 6-12 V rating |
| Milesight UG67 (includes M12 DC power cable and PoE injector) | Gateway |

### Still needed

| Item | Notes |
|---|---|
| Rigid backing sheet for the flexible panel | 1/4 in marine plywood, HDPE, or aluminum, slightly larger than the panel. Not needed if you swap to a rigid framed panel. |
| Stainless bolts, washers, and nylock nuts | To fasten the panel (through its grommets) to the backing sheet, and the sheet to the tilt mount |
| Battery cables, 10 AWG, with ring terminals | Sized to the battery terminals and Rover terminals (check both manuals) |
| Inline fuse holders and fuses | 20-30 A (battery), 10 A (panel, if not in adaptor kit), 5 A (load) |
| 16-18 AWG wire, butt connectors or heat shrink | Load to stabilizer, stabilizer to M12 cable |
| Weatherproof NEMA 4X enclosure, vented | Large enough for the battery, Rover, and stabilizer. Check the battery dimensions first. |
| Cable glands | For wire entry through the bottom of the enclosure |
| Post or pipe, U-bolts, mounting plate | The tilt mount is made for flat surfaces; bolt it to a plate or board, then attach to the post |
| UV-resistant zip ties | Cable management |

### Tools

Wire strippers, crimper, screwdrivers, drill, wrench set, multimeter, heat gun or lighter for heat shrink, and electrical tape.

## Safety rules

1. **Connect in this order: battery, then panel, then load.** The Rover must detect the battery before it sees the panel.
2. **Disconnect in reverse: panel, then load, then battery.**
3. **Never connect the panel to the Rover without a battery attached.** This can damage the controller.
4. **Keep the panel covered or face down while wiring.** It produces voltage whenever light hits it.
5. **Never let battery leads touch.** A LiFePO4 battery can deliver very high current in a short circuit. The battery fuse goes as close to the battery positive as possible.
6. **Follow the Rover and battery manuals** for terminal torque, maximum wire size, and fuse ratings if they differ from this guide.

## Assembly

### Step 1: Prepare the panel and mount

1. Lay the flexible panel on the backing sheet and mark the grommet holes.
2. Drill the holes and fasten the panel with stainless bolts, washers, and nylock nuts. Do not overtighten; the panel should sit flat without being bent or creased.
3. Bolt the backing sheet to the tilt mount rails.
4. Set the tilt as steep as the mount allows (about 60 degrees is ideal for winter sun in the Pacific Northwest).

### Step 2: Prepare the enclosure

1. Mount the Rover and the voltage stabilizer to the enclosure backplate.
2. Place the battery on the floor of the enclosure, secured so it cannot slide.
3. Install cable glands in the bottom of the enclosure: one for the panel cable, one for the gateway cable.
4. Leave space around the Rover for airflow and keep the vent clear.

### Step 3: Connect the battery to the Rover

1. If the battery has a power button, turn it on.
2. Install a 20-30 A inline fuse holder on the positive cable, as close to the battery as possible. **Leave the fuse out for now.**
3. Connect battery negative (-) to the Rover BATTERY (-) terminal.
4. Connect battery positive (+), through the fuse holder, to the Rover BATTERY (+) terminal.
5. Insert the fuse. The Rover display should power on and show battery voltage.

### Step 4: Configure the Rover

1. Plug the BT-2 module into the Rover and pair it with the Renogy app (Renogy DC Home or the current Renogy app).
2. **Battery type:** set to lithium (LI).
3. **Load mode:** set the load output to always on (manual mode in the Rover manual). Do not use dusk-to-dawn or timer modes, which are meant for lighting.
4. **Low voltage disconnect:** leave at the lithium default unless the manual or battery documentation recommends otherwise.
5. Pair the battery's own Bluetooth in the app as well, so you can see state of charge and heater status.

### Step 5: Connect the solar panel

1. Cover the panel or place it face down.
2. Snap the adaptor kit MC4 connectors onto the panel leads, matching positive to positive and negative to negative.
3. Add a 10 A inline fuse on the positive wire if the adaptor kit does not include one.
4. Connect the bare ends to the Rover PV (+) and PV (-) terminals.
5. Uncover the panel. In daylight, the Rover display and app should show charging.

### Step 6: Connect the voltage stabilizer

1. Install a 5 A inline fuse on a positive wire from the Rover LOAD (+) terminal.
2. Connect LOAD (+), through the fuse, to the stabilizer **input** positive.
3. Connect LOAD (-) to the stabilizer **input** negative.
4. Turn on the load output in the app or on the Rover.
5. **Measure the stabilizer output with a multimeter.** It should read about 12 V. Do not continue until it does.

### Step 7: Connect the gateway

1. Check the UG67 quick-start guide for the M12 cable wire colors (typically red is positive, black is negative).
2. Turn the load output off.
3. Connect the M12 cable wires to the stabilizer **output**, positive to positive and negative to negative. Insulate the joints with heat shrink.
4. Remove the protective cap from the UG67 DC port and hand-tighten the M12 plug.
5. Turn the load output on. The gateway should boot within a minute or two.

## Bench test (1 to 2 days)

- [ ] Gateway connects over cellular (Hologram dashboard shows the SIM online)
- [ ] Gateway appears as connected in The Things Network console
- [ ] All four D20-LB sensors report readings in The Things Network
- [ ] Rover app shows the battery charging during the day
- [ ] Load current in the app matches expectations (about 0.3-0.4 A at 12 V)
- [ ] Battery state of charge holds steady or rises over a sunny day

## Field installation

1. **Before transport:** disconnect panel, then load, then battery (remove the battery fuse).
2. **Mount the post** securely; use galvanized or stainless hardware throughout at coastal sites.
3. **Mount the gateway at the top of the post** for the best radio range, using the bracket included with the UG67.
4. **Mount the panel** facing true south at about 60 degrees, where it will not be shaded by the gateway, trees, or structures at any time of day in winter.
5. **Mount the enclosure** lower on the post, above splash and high-water levels.
6. **Reconnect in order:** battery fuse, then panel, then load.
7. **Weatherproof:** tighten cable glands, add drip loops so water runs off before reaching the enclosure or gateway, and secure cables with UV-resistant zip ties.
8. **Confirm** the gateway and all sensors are reporting before leaving the site.

## Maintenance

- Check battery state of charge and charging history in the Renogy app after long cloudy stretches, especially November through January.
- Clean the panel surface a few times a year, or more often if birds or salt spray build up.
- Inspect cable glands, connectors, and fasteners for corrosion at each site visit.
- The D20-LB sensors store readings during gateway outages and upload them once the gateway is back online.

## Troubleshooting

| Symptom | Likely cause | Check |
|---|---|---|
| Rover display off | Battery fuse out or battery switched off | Battery power button, fuse, battery connections |
| Panel not charging | Wiring polarity, blown panel fuse, shade | MC4 connections, fuse, panel voltage with multimeter |
| Gateway not powering on | Load output off, blown load fuse, wiring at stabilizer | Load status in app, 5 A fuse, measure 12 V at stabilizer output |
| Gateway on but offline | Cellular signal or SIM issue | Hologram dashboard, gateway cellular status page |
| Battery draining over several days | Shading or very short winter days | Panel angle and shading; battery heater use in cold weather |
