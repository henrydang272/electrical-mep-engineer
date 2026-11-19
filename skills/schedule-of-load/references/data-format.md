# sol_data.json format

Full worked example: `example_projectA.json` (23 panels, 15 QA items).

```json
{
  "project": "PROJECT A (MAIN CIVIL & MEP)",        // goes into SOL!A1 and PANEL_REG!A1
  "source_note": "Nguồn: 9 bản vẽ SLD ... + Load list ...",       // SOL!A3: which drawings / revisions were used
  "param": {                                                      // optional, PARAM sheet
    "voltage_note": "400V 3-phase 4-wire, 50Hz (spec ...)",       // PARAM!D4
    "cos_phi": 0.8, "cos_note": "Theo Load list ..."              // PARAM!B6 / D6
  },
  "load_list_ref": "Load list CA-E-0001 rev02",                   // optional
  "load_list": { "DB-06B1": [295.6, 369.5, 630, "New LVSG-057"] },// optional: name -> [kW|null, kVA, selected A, fed from]
  "qa_intro_vn": "...", "qa_intro_en": "...",                     // optional QA_LOG!A2/A3
  "panels": [ ... ],
  "qa": [ ["HIGH", "item", "drawing ref", "what was found", "impact", "action / how SOL treats it"] ]
}
```
Priorities: `HIGH` (affects cable size/qty or price), `MED`, `LOW` (note only). Status is written as OPEN.

## panel
```json
{
  "name": "DP06B-001",                         // tag written on the panel box of the SLD
  "dwg": "06B-ZZ-E-7000",                      // short drawing number
  "loc": "NHÀ 6B - ... / PACKAGING ...",       // VN / EN location
  "title": "DISTRIBUTION PANEL ... (Pi 83.5 / Ks 0.8 / Pr 66.8)",   // "Pr <kW>" is read into PANEL_REG kVA
  "inc": [ { "src": "DB-06B1", "desc": "INCOMING FROM DB-06B1",
             "dev": "MCCB", "poles": "4P", "In": 160, "icu": 25, "prot": "VM 0-500V",
             "cable": "1x4C_70 mm2 Cu/XLPE/PVC + 1C_35 mm2 Cu/PVC (E)", "cont": "Khay cáp / Cable tray",
             "here": false, "remark": "Tủ nguồn ghi tag DP06B1-001" } ],
  "ways": [ [ckt, en, vn, kW, kVA, ph, dev, poles, In, Icu, prot, cable, containment, remark], ... ]
}
```

- `here`: true only when the incoming cable is NOT already counted as an outgoing way of a panel in this SOL
  (e.g. fed from a main switchboard by others, or from an existing board). Otherwise false — the cable is counted
  once, at the source panel's outgoing way, and the incoming row shows "(tính tại lộ ra ...)".
- A panel without an SLD: `"title": "không có SDNL - <what is known>"`, one `inc` with `here: false`, `"ways": []`.
- `ph`: `RYB` for 3-phase, `R` / `Y` / `B` for single-phase (drives the current formula in col K).
- `kW` or `kVA` may be `null`; leave both null for SPARE ways (no load → no J/K formulas).
- `ckt` is the real circuit tag from the SLD (L1, EX3, P2, AHU.1, SPARE ...). Never a summary like "3 lộ".
  If the SLD gives no tag, invent an obvious one (L-MCC1) and say so in the remark.

## cable text (col R, parsed into S–X)
Copy it as written on the SLD; the parser understands these shapes:

| written | LIVE (S×T) | NEUTRAL (U×V) | PE (W×X) |
|---|---|---|---|
| `8x1C_185 mm2 Cu/XLPE/PVC + 1C_185 mm2 Cu/PVC (E)` | 1C-185 CXV ×6 | 1C-185 CXV ×2 | PE 1C-185 CV ×1 |
| `4x1C_70mm2 Cu/XLPE/PVC + 1C_35mm2 Cu/PVC (E)` | 1C-70 CXV ×3 | 1C-70 CXV ×1 | PE 1C-35 ×1 |
| `1x4C_70 mm2 Cu/XLPE/PVC + 1C_35 mm2 Cu/PVC (E)` | 4C-70 CXV ×1 | – | PE 1C-35 ×1 |
| `1x3C-2.5mm² Cu/FR/PVC` | 3C-2.5 CVV-FR ×1 | – | – |
| `2x(3C-25mm² Cu/PVC/PVC+E-16mm²)` | 3C-25 CVV ×2 | – | PE 1C-16 ×2 |
| `(chung cáp 5C với L1)` / `""` | nothing counted | | |

Insulation → code: XLPE/FR-PVC → CXV-FR, XLPE → CXV, FR/PVC → CVV-FR, else CVV.
A shared cable (one 5C feeding L1-L2-L3) is written on the first circuit only; the others get
`"(chung cáp 5C với L1)"` so it is not counted three times. Anything the parser cannot read stops the build
with `cannot parse cable: ...` — fix the text rather than the parser unless it is a genuinely new shape.
