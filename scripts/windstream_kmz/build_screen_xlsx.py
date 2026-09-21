# -*- coding: utf-8 -*-
"""Build TBDI Mireye site-screen summary workbook. All data from Mireye pulls
in the 2026-08-11 session (plus flags where county records contradicted Mireye)."""
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

OUT = r"C:\Users\tucke\OneDrive\Documents\Claude\Projects\TBDI Modeling\Mireye\TBDI_Mireye_Site_Screen.xlsx"

# ---------------------------------------------------------------- column spec
# (group, header) in order
COLS = [
    ("Site", "Site"), ("Site", "Lat"), ("Site", "Lng"), ("Site", "Screen depth"),
    ("Parcel (Regrid via Mireye)", "Situs address"),
    ("Parcel (Regrid via Mireye)", "Owner of record"),
    ("Parcel (Regrid via Mireye)", "APN"),
    ("Parcel (Regrid via Mireye)", "Zoning"),
    ("Parcel (Regrid via Mireye)", "Parcel area (m2)"),
    ("Parcel (Regrid via Mireye)", "Parcel area (acres)"),
    ("Parcel (Regrid via Mireye)", "Parcel caveat"),
    ("Power", "ISO/RTO"), ("Power", "Serving utility (retail)"),
    ("Power", "Ind. elec price ($/kWh)"), ("Power", "Est. annual cost ($/MW-yr)"),
    ("Power", "Substation dist (m)"), ("Power", "Substation max kV"),
    ("Power", "Trans line dist (m)"), ("Power", "Trans line kV"),
    ("Power", "Trans line owner"), ("Power", "Max kV within 10 km"),
    ("Power", "Substations in 10 km"), ("Power", "Redundancy flag"),
    ("Power", "County queue (MW, generator-side)"),
    ("Gas / BTM", "Gas pipeline dist (m)"), ("Gas / BTM", "Interstate pipeline (m)"),
    ("Gas / BTM", "Ind. gas ($/MCF)"), ("Gas / BTM", "Grid ($/MWh)"),
    ("Gas / BTM", "Modeled gas gen ($/MWh, fuel-only)"), ("Gas / BTM", "BTM gas flag"),
    ("Flood & Hazard", "FEMA zone"), ("Flood & Hazard", "In SFHA"),
    ("Flood & Hazard", "Seismic design cat."), ("Flood & Hazard", "PGA 2%/50yr (g)"),
    ("Flood & Hazard", "Design wind (mph)"), ("Flood & Hazard", "Karst"),
    ("Flood & Hazard", "Nearest dam (m)"), ("Flood & Hazard", "Dam hazard class"),
    ("Flood & Hazard", "High-hazard dams 10 km"), ("Flood & Hazard", "Shrink-swell"),
    ("Flood & Hazard", "Slope (deg)"),
    ("Climate / Cooling", "Design wet bulb (degC)"), ("Climate / Cooling", "Days >=32C /yr"),
    ("Climate / Cooling", "Free cooling h/yr @15C"), ("Climate / Cooling", "Free cooling h/yr @10C"),
    ("Air & Environment", "Ozone nonattainment"), ("Air & Environment", "Worst class"),
    ("Air & Environment", "Maintenance area"), ("Air & Environment", "Superfund in 8 km"),
    ("Air & Environment", "Brownfields in 8 km"), ("Air & Environment", "USTs in 1 km"),
    ("Air & Environment", "Open LUST in 1 km"), ("Air & Environment", "Opportunity Zone"),
    ("Air & Environment", "Incentive stack"),
    ("Water / Sewer", "In water service area"), ("Water / Sewer", "Water system"),
    ("Water / Sewer", "System pop served"), ("Water / Sewer", "In sewer service area"),
    ("Water / Sewer", "Sewer provider"), ("Water / Sewer", "WWTP dist (m)"),
    ("Water / Sewer", "WWTP pop served"),
    ("Connectivity", "FTTP providers"), ("Connectivity", "5G class"),
    ("Neighbors", "Housing units 1 km"), ("Neighbors", "Density (units/km2)"),
    ("Neighbors", "Residential context"), ("Neighbors", "School dist (m)"),
    ("Neighbors", "School name"),
    ("Summary", "Rank"), ("Summary", "Key strengths"), ("Summary", "Key risks"),
    ("Summary", "Verdict"), ("Summary", "Recommendation"),
]

A = "absent"      # source confirmed no data (a real answer)
NP = "not pulled" # field not requested / credits

# ---------------------------------------------------------------- site rows
SITES = [
 # Boyd KY (test screen)
 dict(site="Ashland, Boyd Co KY", lat=38.4758, lng=-82.64385, depth="Full (greenfield recipe - predates conversion recipe; no building/conversion fields)",
  paddr=NP, powner=NP, papn=NP, pzone="R-5", pm2=4388.49, pcav="Single-point Regrid match - FRAGMENT RISK: R-5/1.08-ac may be adjacent lot if site is a multi-parcel assemblage (Northfield pattern); county check needed",
  iso=NP, util="Kentucky Power Co", price=0.073, cost=639480,
  subm=1446.8, subkv=69, linem=695.8, linekv=69, lineown="Kentucky Power Co", maxkv=69, subs=15, red="TRUE", queue=A,
  gasm=6713.6, igasm=6713.6, gasp=4.51, grid=73.0, gasgen=41.32, btm="TRUE",
  zone="X", sfha="No", sdc="B", pga=0.135, wind=112, karst="No", damm=9078.4, damh="High", hhd=2, shrink="Low", slope=1.21,
  wb=25.0, d32=28, fc15=4531, fc10=3434,
  nonatt="No", wcls=A, maint="No", sf=10, bf=21, ust=34, lust=0, oz="No", stack="(none)",
  wat="Yes", wsys="Ashland Water Works", wpop=44402, sew="Yes", sprov="Ashland", wwm=1771, wwpop=21481,
  fiber=2, g5="5g_high_speed", hu=1735, dens=381.1, ctx="dense", schm=221, schn="Ashland Child Development Center",
  rank=9, stg="Operating facility (established use); Zone X; flat; water+sewer in-area; best OH-valley gas economics ($41 vs $73 grid); 345 kV substation 6.6 km",
  rsk="69 kV ceiling in radius caps ~5-15 MW; expansion friction from dense residential + childcare 221 m; parcel zoning/size unverified (fragment risk); greenfield-recipe screen only",
  verdict="REVIEW (5-15 MW band)", rec="Keep as low-band expansion candidate; re-screen with conversion recipe + county assemblage check after Sept 1"),
 # Baldwin GA
 dict(site="Baldwin GA - 2000 Communications Blvd", lat=34.49720847, lng=-83.54997767, depth="Full (conversion screen)",
  paddr="2000 COMMUNICATIONS BLVD", powner=A, papn="090 016", pzone="HI", pm2=106647.29,
  pcav="Validated: coord + address pulls returned same parcel; address exact match",
  iso=A, util="Georgia Power Co", price=0.0684, cost=599184,
  subm=1300.6, subkv=115, linem=169.5, linekv=115, lineown="Georgia Power Co", maxkv=115, subs=10, red="TRUE", queue=A,
  gasm=A, igasm=51825.7, gasp=5.56, grid=68.4, gasgen=50.94, btm=A,
  zone="X", sfha="No", sdc="C", pga=0.195, wind=112, karst="No", damm=3629.9, damh="Low", hhd=3, shrink="Low", slope=0.35,
  wb=24.5, d32=24, fc15=4154, fc10=2717,
  nonatt="No", wcls=A, maint="No", sf=0, bf=2, ust=1, lust=0, oz="No", stack="(none)",
  wat="No (54 m to boundary)", wsys=A, wpop=A, sew="Yes", sprov="Baldwin WPCP", wwm=2067, wwpop=5231,
  fiber=1, g5="5g_high_speed", hu=778, dens=136.4, ctx="dense", schm=1249, schn="Baldwin Elementary School",
  rank=1, stg="Operating facility + 26.35-ac HI parcel for expansion; 115 kV line 170 m; attainment air; clean environmental radius; full 5-50 MW band",
  rsk="No gas fallback (interstate 52 km); outside water area (54 m extension); small WWTP (5,231); no queue visibility (non-RTO)",
  verdict="GO", rec="Pursue first - open Georgia Power capacity inquiry now"),
 # Northfield OH
 dict(site="Northfield OH - 54 Leonard Ave", lat=41.31474448, lng=-81.53703932, depth="Full (conversion screen)",
  paddr="LEONARD AVE", powner="Kinetic ABS OH LLC", papn="4002466", pzone="T-C", pm2=463.24,
  pcav="FRAGMENT - wrong parcel for address; county shows 7-parcel assemblage (APNs 4002461-4002467); building on 4002461",
  iso="PJM", util="City of Cleveland (OH) - SUSPECT", price=0.0995, cost=871620,
  subm=1090.9, subkv=A, linem=893.1, linekv=345, lineown=A, maxkv=345, subs=23, red="TRUE", queue=A,
  gasm=534.6, igasm=24864.2, gasp=11.23, grid=99.5, gasgen=102.88, btm="TRUE",
  zone="X", sfha="No", sdc="B", pga=0.095, wind=112, karst="No", damm=1699.4, damh="High", hhd=3, shrink="Low", slope=3.77,
  wb=24.1, d32=8, fc15=5538, fc10=4258,
  nonatt="Yes - ozone (2015 std)", wcls="Serious", maint="Yes (2008 ozone)", sf=7, bf=2, ust=4, lust=2, oz="No", stack="(none)",
  wat="Yes", wsys="Cleveland Public Water System", wpop=1308955, sew="Yes", sprov="NEORSD Southerly WWTP", wwm=7099, wwpop=21809,
  fiber=4, g5="5g_high_speed", hu=1137, dens=196.8, ctx="dense", schm=87, schn="Nordonia Middle School",
  rank=3, stg="Operating facility (established use beside school); best wires in portfolio - 345 kV line 893 m, 23 substations/10 km; 1.3M-person water system; 4 fiber providers; strong cooling",
  rsk="Serious ozone (incremental genset permitting, netting possible vs existing permits); $872k/MW-yr power; parcel data unreliable (7-parcel assemblage); utility attribution suspect; nearest UST 30 m likely own fuel tank",
  verdict="REVIEW", rec="Rises under operating-facility lens - verify serving utility (FirstEnergy?) + assemblage, then utility capacity inquiry on the 345 kV path"),
 # Hudson OH
 dict(site="Hudson OH - 1300 Terex Rd", lat=41.21706309, lng=-81.44250817, depth="Full (conversion screen)",
  paddr="1300 TEREX RD", powner="Kinetic ABS OH LLC", papn="3003811", pzone="DISTRICT-8", pm2=3254.56,
  pcav="Single matched parcel; owner holds 16 Summit Co parcels - may be part of assemblage",
  iso="PJM", util="City of Hudson (OH) - verified real muni", price=0.0995, cost=871620,
  subm=1054.1, subkv=138, linem=814.1, linekv=A, lineown=A, maxkv=138, subs=21, red="TRUE", queue=A,
  gasm=724.0, igasm=30645.3, gasp=11.23, grid=99.5, gasgen=102.88, btm="TRUE",
  zone="X", sfha="No", sdc="B", pga=0.085, wind=112, karst="No", damm=2007.5, damh="Significant", hhd=5, shrink="Low", slope=1.29,
  wb=24.0, d32=8, fc15=5448, fc10=4240,
  nonatt="Yes - ozone (2015 std)", wcls="Serious", maint="Yes (2008 ozone)", sf=1, bf=3, ust=3, lust=0, oz="No", stack="(none)",
  wat="Yes", wsys="Hudson City PWS", wpop=8385, sew="No (546 m to boundary)", sprov=A, wwm=6095, wwpop=16758,
  fiber=4, g5="5g_high_speed", hu=944, dens=86.3, ctx="dense", schm=256, schn="The Goddard School",
  rank=4, stg="Operating facility; 138 kV substation 1.1 km; 21 substations/10 km; clean environmental; strong cooling; 4 fiber providers",
  rsk="Municipal utility counterparty at 50 MW; Serious ozone (incremental gensets need Tier 4); outside sewer area; small water system",
  verdict="REVIEW", rec="Advance - gauge Hudson Public Power capacity appetite for the increment; spec Tier 4 gensets"),
 # Newark OH
 dict(site="Newark OH - 66 N 4th St", lat=40.05944853, lng=-82.40487305, depth="Full (conversion screen)",
  paddr="66 N 4 ST", powner="Kinetic ABS OH LLC", papn="02121190402004058000", pzone="DC", pm2=1113.45,
  pcav="Single matched parcel; downtown CBD - possible assemblage",
  iso="PJM", util="Ohio Power Co (AEP)", price=0.0995, cost=871620,
  subm=928.1, subkv=A, linem=605.7, linekv=69, lineown="Ohio Power Co", maxkv=69, subs=21, red="TRUE", queue=710.04,
  gasm=2707.6, igasm=2707.6, gasp=11.23, grid=99.5, gasgen=102.88, btm="TRUE",
  zone="X", sfha="No", sdc="B", pga=0.085, wind=112, karst="No", damm=3160.8, damh="Significant", hhd=0, shrink="Low", slope=0.84,
  wb=24.6, d32=11, fc15=5045, fc10=3940,
  nonatt="No", wcls=A, maint="Yes (2008+2015 ozone)", sf=5, bf=16, ust=16, lust=1, oz="No", stack="brownfield_repowering_screened",
  wat="Yes", wsys="Newark City PWS", wpop=49934, sew="Yes", sprov="Newark WWTP & Sewer System", wwm=2889, wwpop=10538,
  fiber=3, g5="5g_high_speed", hu=3135, dens=541.4, ctx="dense", schm=182, schn="Child Of God Preschool",
  rank=8, stg="Operating facility (established downtown use); solid AEP counterparty; maintenance-only air (best air status in the OH group); water+sewer in-area; 710 MW county queue",
  rsk="69 kV ceiling in entire radius caps ~5-15 MW; nearest UST 33 m likely own tank but 16 USTs/16 brownfields in downtown radius (diligence); expansion friction from preschool 182 m + density",
  verdict="REVIEW (5-15 MW band)", rec="Keep as low-band expansion candidate - AEP capacity inquiry decides it"),
 # Riverside TX
 dict(site="Riverside TX - FM 980 (Walker Co)", lat=30.85154, lng=-95.40012, depth="Full (conversion screen)",
  paddr="FM 980", powner="Valor Telecommunications of Texas LP", papn="14123", pzone=A, pm2=2327.99,
  pcav="Single matched parcel; rural - assemblage unknown",
  iso="ERCOT (field) - SUSPECT, wires are Entergy TX (likely MISO)", util="Mid-South Electric Coop Assn", price=0.0633, cost=554508,
  subm=1467.8, subkv=138, linem=802.7, linekv=69, lineown="Entergy Texas, Inc.", maxkv=138, subs=2, red="FALSE", queue=150,
  gasm=544.7, igasm=544.7, gasp=3.12, grid=63.3, gasgen=28.58, btm="TRUE",
  zone="A", sfha="YES - SFHA, no BFE published", sdc="B", pga=0.045, wind=112, karst="No", damm=1640.0, damh="Low", hhd=2, shrink="Low", slope=0.85,
  wb=26.2, d32=104, fc15=2693, fc10=1460,
  nonatt="No", wcls=A, maint="No", sf=0, bf=0, ust=2, lust=0, oz="No", stack="(none)",
  wat="Yes", wsys="Riverside SUD", wpop=6492, sew="No (7,460 m to boundary)", sprov=A, wwm=10865, wwpop=3010,
  fiber=1, g5="5g_high_speed", hu=315, dens=32.2, ctx="moderate", schm=9750, schn="(unreliable Overture record)",
  rank=10, stg="Operating facility already living with the flood zone; cheapest grid ($555k/MW-yr); best usable gas hedge ($29 vs $63, pipeline 545 m, attainment air); 138 kV",
  rsk="FEMA Zone A (no BFE) - substantial-improvement rule bites densification capex >50% of building value regardless of existing ops; worst-tier cooling; 2 substations/10 km, redundancy FALSE; sewer 7.5 km",
  verdict="NO-GO (flood)", rec="Park - spend ~$2k on elevation certificate; revive only if LOMA path viable"),
 # Harrison AR
 dict(site="Harrison AR - 202 Graham St", lat=36.214283, lng=-93.079052, depth="Full (conversion screen)",
  paddr="202 GRAHAM STRE", powner=A, papn="825-14426-200", pzone="C3", pm2=40473.46,
  pcav="Single matched parcel - 10.0 ac; only multi-acre parcel besides Baldwin",
  iso="MISO", util="Entergy Arkansas LLC", price=0.062, cost=543120,
  subm=960.6, subkv=161, linem=960.6, linekv=161, lineown="Entergy Arkansas Inc", maxkv=161, subs=3, red="TRUE", queue=A,
  gasm=5124.3, igasm=62989.5, gasp=9.28, grid=62.0, gasgen=85.01, btm="TRUE (flag only - see risks)",
  zone="X", sfha="No", sdc="D", pga=0.225, wind=112, karst="YES - carbonate, EXPOSED (Boone Fm)", damm=A, damh=A, hhd=0, shrink=A, slope=2.58,
  wb=25.6, d32=38, fc15=4294, fc10=2981,
  nonatt="No", wcls=A, maint="No", sf=0, bf=0, ust=3, lust=0, oz="No", stack="(none)",
  wat="Yes", wsys="Harrison Waterworks", wpop=17455, sew="Yes", sprov="Harrison WWTP", wwm=2947, wwpop=13468,
  fiber=3, g5="5g_high_speed", hu=388, dens=38.4, ctx="moderate", schm=1158, schn="Educational Opportunity Center",
  rank=2, stg="Operating facility + 10.0-ac C3 parcel for expansion; 161 kV substation+line ~960 m; cheapest power in portfolio ($543k/MW-yr); attainment; spotless environmental",
  rsk="Exposed carbonate karst + seismic design cat. D - governs NEW expansion structures (existing building's decades of service partly de-risk); only 3 substations/10 km; gas gen uneconomic",
  verdict="GO (leaning)", rec="Pursue #2 - geotech karst study for expansion footprint + Entergy capacity inquiry in parallel"),
 # Moultrie GA
 dict(site="Moultrie GA - 216 4th St SE", lat=31.17748292, lng=-83.78371355, depth="Full (conversion screen)",
  paddr="216 4TH ST SE", powner=A, papn="M035  001", pzone="C-3", pm2=5286.65,
  pcav="Single matched parcel - 1.31 ac",
  iso=A, util="City of Moultrie (GA) - muni", price=0.0684, cost=599184,
  subm=565.6, subkv=115, linem=302.9, linekv=115, lineown="Georgia Power Co", maxkv=115, subs=15, red="TRUE", queue=130,
  gasm=4850.7, igasm=4850.7, gasp=5.56, grid=68.4, gasgen=50.94, btm="TRUE",
  zone="X", sfha="No", sdc="B", pga=0.065, wind=112, karst="Buried carbonate (low confidence)", damm=2624.8, damh="Low", hhd=1, shrink="Low", slope=0.94,
  wb=26.4, d32=69, fc15=2658, fc10=1372,
  nonatt="No", wcls=A, maint="No", sf=0, bf=2, ust=32, lust=2, oz="YES - tract 13071970702", stack="opportunity_zone",
  wat="Yes", wsys="Moultrie", wpop=17067, sew="Yes", sprov="Moultrie WPCP", wwm=2852, wwpop=13760,
  fiber=1, g5="5g_high_speed", hu=1285, dens=188.2, ctx="dense", schm=775, schn="Stringfellow Elementary School",
  rank=5, stg="Operating facility; only Opportunity Zone site (capital-stack sweetener); 115 kV line 303 m (GA Power wires); attainment; 15 substations/10 km",
  rsk="Muni retail counterparty; nearest UST 31 m likely own tank but 32 USTs + 2 open LUST in 1 km (Phase I); hot climate (69 days >=32C); 1.31-ac parcel",
  verdict="REVIEW", rec="Hold as OZ-advantaged backup; Phase I environmental if advanced"),
 # Newton IA
 dict(site="Newton IA - 115 S 2nd Ave W", lat=41.6983315, lng=-93.05448565, depth="Full (conversion screen)",
  paddr="115 S 2ND AVE W", powner="CSL Iowa System LLC (Uniti leaseback)", papn="0834158001", pzone="C-CBD", pm2=1731.00,
  pcav="Single matched parcel; downtown CBD - possible assemblage",
  iso="MISO", util="Consumers Energy - SUSPECT (likely Alliant/IPL; a Consumers Energy Coop exists in IA)", price=0.0626, cost=548376,
  subm=784.2, subkv=161, linem=751.7, linekv=A, lineown="MidAmerican Energy Co", maxkv=161, subs=4, red="TRUE", queue=A,
  gasm=4438.6, igasm=4438.6, gasp=6.69, grid=62.6, gasgen=61.29, btm="TRUE",
  zone="X", sfha="No", sdc="B", pga=0.045, wind=112, karst="No", damm=2844.3, damh="Low", hhd=0, shrink="Moderate", slope=2.88,
  wb=26.7, d32=16, fc15=5312, fc10=4331,
  nonatt="No", wcls=A, maint="No", sf=1, bf=0, ust=23, lust=2, oz="No", stack="brownfield_repowering_screened",
  wat="Yes", wsys="Newton Water Supply", wpop=16518, sew="Yes", sprov="Newton WWTP", wwm=274, wwpop=16283,
  fiber=3, g5="5g_high_speed", hu=2685, dens=494.5, ctx="dense", schm=426, schn="Central Junior High School",
  rank=6, stg="Operating facility; 161 kV substation 784 m; cheap power ($548k/MW-yr); attainment; excellent cooling (5,312 h)",
  rsk="0.43-ac CBD fragment (assemblage unknown); Uniti (CSL) leaseback ownership - counterparty differs; utility attribution suspect; superfund 827 m + 2 open LUST (diligence); expansion friction from junior high 426 m",
  verdict="REVIEW", rec="Hold - verify Alliant service, assemblage, and Uniti lease terms; mid-tier"),
 # Sugar Land TX
 dict(site="Sugar Land TX - Fort Bend Co", lat=29.63625224, lng=-95.59818132, depth="TRIAGE ONLY (credits) - no parcel/building/school",
  paddr=NP, powner=NP, papn=NP, pzone=NP, pm2=NP,
  pcav="Parcel fields not pulled - credit exhaustion; complete after Sept 1 reset",
  iso="ERCOT (eGRID ERCT)", util="CenterPoint Energy (wires; retail via competitive REP)", price=0.0633, cost=554508,
  subm=913.6, subkv=138, linem=NP, linekv=NP, lineown=NP, maxkv=NP, subs=18, red="TRUE", queue=3320.46,
  gasm=615.1, igasm=726.7, gasp=3.12, grid=63.3, gasgen=28.58, btm="TRUE",
  zone="X", sfha="No", sdc="A", pga=0.045, wind=136, karst="No", damm=3892.1, damh="High", hhd=1, shrink="VERY HIGH", slope=1.37,
  wb=27.1, d32=106, fc15=1994, fc10=1032,
  nonatt="Yes - ozone (2008+2015 stds)", wcls="SEVERE", maint="No", sf=1, bf=2, ust=5, lust=0, oz="No", stack="brownfield_repowering_screened",
  wat="Yes", wsys="City of Sugar Land", wpop=90909, sew="Yes", sprov="Sugar Land North WWTP", wwm=2299, wwpop=1239,
  fiber=4, g5="5g_high_speed", hu=1677, dens=296.4, ctx="dense", schm=NP, schn=NP,
  rank=7, stg="Operating facility; Zone X despite Houston metro; 18 substations/10 km; 3.3 GW county queue (hot market); best gas economics on paper; nearest UST 29 m likely own tank",
  rsk="SEVERE ozone (25 tpy NOx major threshold - neutralizes gas play, forces Tier 4 on incremental gensets); 136 mph design wind; very-high shrink-swell clays; worst cooling (1,994 h); screen incomplete",
  verdict="REVIEW (incomplete)", rec="Complete parcel screen after Sept 1 credit reset before judging"),
]

KEYS = ["site","lat","lng","depth","paddr","powner","papn","pzone","pm2","ACRES","pcav",
 "iso","util","price","cost","subm","subkv","linem","linekv","lineown","maxkv","subs","red","queue",
 "gasm","igasm","gasp","grid","gasgen","btm",
 "zone","sfha","sdc","pga","wind","karst","damm","damh","hhd","shrink","slope",
 "wb","d32","fc15","fc10",
 "nonatt","wcls","maint","sf","bf","ust","lust","oz","stack",
 "wat","wsys","wpop","sew","sprov","wwm","wwpop",
 "fiber","g5","hu","dens","ctx","schm","schn",
 "rank","stg","rsk","verdict","rec"]
assert len(KEYS) == len(COLS), (len(KEYS), len(COLS))

# ---------------------------------------------------------------- styling
ARIAL = "Arial"
GROUP_FILLS = {
    "Site": "1F3864", "Parcel (Regrid via Mireye)": "2E5A46", "Power": "7A4A00",
    "Gas / BTM": "5A3E7A", "Flood & Hazard": "7A2020", "Climate / Cooling": "1F5F6B",
    "Air & Environment": "4A5A23", "Water / Sewer": "1F4E79", "Connectivity": "555555",
    "Neighbors": "6B3A5B", "Summary": "000000",
}
VERDICT_FILL = {"GO": "C6EFCE", "GO (leaning)": "C6EFCE", "REVIEW": "FFEB9C",
                "REVIEW (incomplete)": "FFEB9C", "REVIEW (5-15 MW band)": "FFEB9C",
                "NO-GO": "FFC7CE", "NO-GO (flood)": "FFC7CE"}
VERDICT_FONTC = {"GO": "006100", "GO (leaning)": "006100", "REVIEW": "9C6500",
                 "REVIEW (incomplete)": "9C6500", "REVIEW (5-15 MW band)": "9C6500",
                 "NO-GO": "9C0006", "NO-GO (flood)": "9C0006"}

wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Site Screen"

thin = Side(style="thin", color="BFBFBF")
border = Border(left=thin, right=thin, top=thin, bottom=thin)

# group header row (row 1) with merges
col = 1
prev_group = None
group_start = 1
for i, (grp, hdr) in enumerate(COLS, start=1):
    if grp != prev_group:
        if prev_group is not None and i - 1 > group_start:
            ws.merge_cells(start_row=1, start_column=group_start, end_row=1, end_column=i - 1)
        elif prev_group is not None:
            pass
        group_start = i
        c = ws.cell(row=1, column=i, value=grp)
        c.font = Font(name=ARIAL, bold=True, color="FFFFFF", size=10)
        c.fill = PatternFill("solid", fgColor=GROUP_FILLS[grp])
        c.alignment = Alignment(horizontal="center", vertical="center")
        prev_group = grp
# close last merge
last_idx = len(COLS)
if last_idx > group_start:
    ws.merge_cells(start_row=1, start_column=group_start, end_row=1, end_column=last_idx)
# fill merged group cells' background
col = 1
for i, (grp, hdr) in enumerate(COLS, start=1):
    c = ws.cell(row=1, column=i)
    c.fill = PatternFill("solid", fgColor=GROUP_FILLS[grp])
    c.border = border

# field header row (row 2)
for i, (grp, hdr) in enumerate(COLS, start=1):
    c = ws.cell(row=2, column=i, value=hdr)
    c.font = Font(name=ARIAL, bold=True, size=9)
    c.fill = PatternFill("solid", fgColor="D9D9D9")
    c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    c.border = border

# data rows
M2_COL = KEYS.index("pm2") + 1
for r, s in enumerate(SITES, start=3):
    for i, k in enumerate(KEYS, start=1):
        if k == "ACRES":
            v = s["pm2"]
            if isinstance(v, (int, float)):
                cell = ws.cell(row=r, column=i, value=f"={get_column_letter(M2_COL)}{r}/4046.856")
                cell.number_format = "0.00"
            else:
                ws.cell(row=r, column=i, value=v)  # absent / not pulled
        else:
            v = s[k]
            cell = ws.cell(row=r, column=i, value=v)
            if k == "pm2" and isinstance(v, (int, float)):
                cell.number_format = "#,##0"
            elif k in ("cost", "wpop", "wwpop", "hu") and isinstance(v, (int, float)):
                cell.number_format = "#,##0"
            elif k in ("subm","linem","gasm","igasm","damm","wwm","schm","fc15","fc10") and isinstance(v,(int,float)):
                cell.number_format = "#,##0"
            elif k == "price" and isinstance(v, (int, float)):
                cell.number_format = "$0.0000"
            elif k in ("gasp","grid","gasgen","dens","slope","wb","pga") and isinstance(v,(int,float)):
                cell.number_format = "0.00"
            elif k == "queue" and isinstance(v, (int, float)):
                cell.number_format = "#,##0.0"
        c = ws.cell(row=r, column=i)
        c.font = Font(name=ARIAL, size=9)
        c.border = border
        c.alignment = Alignment(vertical="top", wrap_text=(KEYS[i-1] in ("site","depth","pcav","util","iso","stg","rsk","rec","karst","sfha","btm","schn","wsys","sprov","nonatt","maint","oz","powner","sew","wat")))
    # verdict formatting
    vi = KEYS.index("verdict") + 1
    vc = ws.cell(row=r, column=vi)
    vv = vc.value
    if vv in VERDICT_FILL:
        vc.fill = PatternFill("solid", fgColor=VERDICT_FILL[vv])
        vc.font = Font(name=ARIAL, size=9, bold=True, color=VERDICT_FONTC[vv])
    # absent/not pulled greyed
    for i, k in enumerate(KEYS, start=1):
        cc = ws.cell(row=r, column=i)
        if cc.value in (A, NP):
            cc.font = Font(name=ARIAL, size=9, italic=True, color="808080")

# widths
WIDE = {"site":30,"depth":22,"paddr":20,"powner":24,"papn":18,"pcav":36,"util":30,"iso":22,
        "stg":48,"rsk":52,"rec":42,"karst":22,"schn":24,"wsys":22,"sprov":22,"stack":22,
        "nonatt":18,"sfha":18,"btm":16,"lineown":20,"verdict":14,"sew":16,"wat":16}
for i, k in enumerate(KEYS, start=1):
    ws.column_dimensions[get_column_letter(i)].width = WIDE.get(k, 11)
ws.freeze_panes = "B3"
ws.row_dimensions[2].height = 40

# ---------------------------------------------------------------- notes sheet
ns = wb.create_sheet("Notes & Caveats")
notes = [
 ("TBDI x Mireye site screen - data notes", ""),
 ("Session", "All values pulled via mireye-earth MCP on 2026-08-11. Sources per field: FEMA NFHL, EIA Power Atlas, Regrid, EPA (Green Book/FRS/UST Finder/Sewersheds/CWS/CWNS), LBNL Queued Up, NREL NSRDB, NOAA/ASCE, USGS (NSHM/karst/3DEP/landslide), USACE NID, Census TIGERweb, FCC BDC, Overture."),
 ("", ""),
 ("OPERATING-FACILITY LENS", "Per Tucker (2026-08-11): all candidate sites are already OPERATING data centers/telecom facilities. Verdicts are therefore scored as brownfield capacity EXPANSION, not new-use siting: school/residential-density findings are expansion friction (noise, construction, incremental permits), NOT use-permission knockouts - the existing use is established/grandfathered. Zoning of record (e.g. R-5 at Ashland, T-C at Northfield) likewise does not block an existing use, only complicates expansion. What the lens does NOT change: wires (voltage ceilings cap the MW band), flood (substantial-improvement rule still bites densification capex), climate/cooling, geology, and counterparty structure."),
 ("Nearest-UST pattern", "Nearest UST distances of ~29-33 m at Northfield, Newark, Moultrie and Sugar Land are most plausibly the facilities' OWN registered backup-fuel tanks - normal operating infrastructure, not third-party contamination risk. Wider-radius UST/brownfield/LUST counts remain genuine diligence items."),
 ("'absent' vs 'not pulled'", "'absent' = the source confirmed no data exists there (a real answer, e.g. no dam within 10 km). 'not pulled' = field was never requested (Boyd test screen used a different recipe; Sugar Land hit the monthly credit ceiling)."),
 ("Parcel areas are FLOORS, not site sizes", "Regrid returns the single parcel under the query point. Telecom exchanges are frequently multi-parcel assemblages: at Northfield OH, county records show a 7-parcel site and Mireye returned a 0.11-ac vacant fragment twice (coordinate AND rooftop-geocoded address), with every quality flag clean. Treat every small parcel value as a fragment until county records confirm. Only Baldwin GA was cross-validated (two independent pulls returned the identical 26.35-ac parcel)."),
 ("Serving-utility field", "Retail biller only - never the transmission owner or interconnection counterparty. Two values look wrong (overlapping-territory polygon errors): Northfield 'City of Cleveland' (expected FirstEnergy/Ohio Edison) and Newton 'Consumers Energy' (expected Alliant/IPL; note a real Consumers Energy Coop exists in Iowa). Verify against the site's actual power invoices."),
 ("County queue (MW)", "LBNL Queued Up tracks GENERATOR interconnection queues. Read as grid congestion / market-activity signal, never as capacity available to serve load."),
 ("Deliverable MW", "Not derivable from these fields. Feeder/transformer headroom requires a utility capacity study per site (contract-gated Mireye power-band product also exists)."),
 ("Ozone nonattainment at 5-50 MW grid-primary", "Constraint on the backup genset fleet, not the grid draw. Major-source NOx thresholds: 100 tpy attainment / 50 tpy Serious / 25 tpy Severe. ~5 MW fleets are minor everywhere; ~50 MW fleets in Serious/Severe areas need Tier 4/SCR engines + capped test hours (~15-25% genset capex premium, longer permitting). Severe status also forecloses non-emergency running - it neutralizes Sugar Land's behind-the-meter gas advantage."),
 ("Building fields (Overture)", "Excluded as unreliable: footprint was ~10x off at Northfield vs. owner records; class/floor labels missing at most sites. Use owner-provided interior square footage instead."),
 ("Riverside TX flood", "Zone A = SFHA mapped by approximate methods, NO base flood elevation published. Substantial-improvement rule likely triggered by any conversion. Cheapest resolution: elevation certificate + LOMA attempt (~$1-3k) before any further spend."),
 ("MW band rule of thumb", "69 kV network: low tens of MW where headroom exists. 115-161 kV: comfortably covers 50 MW. 345 kV tap: only pencils at the very top of the range."),
 ("Ownership pattern", "Sites sit in different Windstream entities: Kinetic ABS OH LLC (OH sites, ABS vehicle, Dec 2025 transfers), CSL Iowa System LLC (Uniti leaseback), Valor Telecommunications of Texas LP. Negotiating counterparty differs by site."),
 ("Credit state", "Free plan 5,000/mo effectively exhausted (~4,999 used); resets 2026-09-01. Outstanding: Sugar Land parcel/school fields (~310 credits). Session total ~5,000 credits across 10 screens (screens ran ~450 each after recipe was tuned; early Boyd screen + missteps cost more)."),
 ("Verdicts", "GO = advance to diligence now. REVIEW = real candidate with named blockers to resolve first. REVIEW (5-15 MW band) = viable only at the low end of the 5-50 MW target due to 69 kV wires. NO-GO = disqualified on current facts. Under the operating-facility lens the only siting NO-GO left is Riverside's floodplain - the portfolio is otherwise a power-expansion ranking (wires x yard space x permitting increment)."),
 ("Rank", "1 Baldwin GA, 2 Harrison AR, 3 Northfield OH (rises on 345 kV once school objection reframed), 4 Hudson OH, 5 Moultrie GA, 6 Newton IA, 7 Sugar Land TX (incomplete), 8 Newark OH (5-15 MW band), 9 Ashland KY (5-15 MW band; greenfield-recipe screen only, parcel fragment risk), 10 Riverside TX (flood; potentially resolvable via ~$2k elevation certificate/LOMA)."),
]
for r, (a, b) in enumerate(notes, start=1):
    ca = ns.cell(row=r, column=1, value=a); ca.font = Font(name=ARIAL, bold=True, size=10)
    cb = ns.cell(row=r, column=2, value=b); cb.font = Font(name=ARIAL, size=10)
    cb.alignment = Alignment(wrap_text=True, vertical="top")
ns.column_dimensions["A"].width = 34
ns.column_dimensions["B"].width = 130
ns.cell(row=1, column=1).font = Font(name=ARIAL, bold=True, size=13)

wb.save(OUT)
print("saved", OUT)
