const pptxgen = require('pptxgenjs');
const D = require('/home/user/Claude/vi-capacity-data.json');

const p = new pptxgen();
p.layout = 'LAYOUT_WIDE';            // 13.333 x 7.5
p.author = 'Vi AI-NOC capacity model';
p.title  = 'Vi AI-NOC Capacity Model';

/* palette - carried from the capacity report, CVD-validated */
const C = {
  paper:'F4F5F2', card:'FFFFFF', ink:'171A18', ink2:'3E453F', ink3:'6A726B',
  rule:'D9DCD4', sunk:'EDEFE9',
  teal:'008E7F', rust:'B04A12',
  dark:'12211E', dcard:'1B2C28', dink:'E9ECE7', dink2:'A9B3AB', dink3:'8A968C',
  dteal:'00A896', drust:'CB6127', drule:'2C3E39',
};
const F = {d:'Arial', b:'Calibri', m:'Courier New'};
const M = 0.55, W = 13.333, USE = W - 2*M;

/* one filled square - the motif, repeated on both slides */
const sq = (s,x,y,c,sz) => s.addShape(p.ShapeType.rect,
  {x, y, w:sz||0.075, h:sz||0.075, fill:{color:c}, line:{type:'none'}});

const card = (s,x,y,w,h,dark) => s.addShape(p.ShapeType.roundRect, {
  x,y,w,h, rectRadius:0.05,
  fill:{color: dark ? C.dcard : C.card},
  line:{color: dark ? C.drule : C.rule, width:0.75},
});

const head = (s,x,y,w,t,c) => s.addText(t, {
  x,y,w,h:0.24, isTextBox:true, margin:0, fontFace:F.d, fontSize:10,
  bold:true, color:c, charSpacing:1.1,
});

/* ================================================================ SLIDE 1 */
const s1 = p.addSlide();
s1.background = {color: C.paper};

s1.addText('How the fleet number is derived', {
  x:M, y:0.36, w:USE, h:0.5, isTextBox:true, margin:0,
  fontFace:F.d, fontSize:29, bold:true, color:C.ink, charSpacing:-0.4,
});
s1.addText([
  {text:'Vi AI-NOC · RAN fault management', options:{color:C.teal, bold:true}},
  {text:'   ·   ~2M cells, ~10M alarms/day   ·   serving capacity measured with GuideLLM 0.7.3, demand derived from the SoW',
   options:{color:C.ink3}},
], {x:M, y:0.88, w:USE, h:0.28, isTextBox:true, margin:0, fontFace:F.b, fontSize:11.5});

const CY = 1.42, CH = 5.5, CW = (USE - 0.6)/3;
const CX = [M, M+CW+0.3, M+2*(CW+0.3)];

/* ---- col 1 : assumptions ---- */
card(s1, CX[0], CY, CW, CH);
sq(s1, CX[0]+0.24, CY+0.28, C.teal);
head(s1, CX[0]+0.40, CY+0.20, CW-0.6, 'ASSUMPTIONS', C.ink);

s1.addText('FIXED — from the SoW', {
  x:CX[0]+0.24, y:CY+0.56, w:CW-0.48, h:0.2, isTextBox:true, margin:0,
  fontFace:F.d, fontSize:8.5, bold:true, color:C.teal, charSpacing:0.9});
s1.addText([
  {text:'~2M cells · ~10M alarms/day · 70% RAN-linked', options:{bullet:true, breakLine:true}},
  {text:'KPIs ≈285 GB/day · logs ≈30 GB/day', options:{bullet:true, breakLine:true}},
  {text:'~9.2 TB logical, 2-week hot window', options:{bullet:true, breakLine:true}},
  {text:'Private / on-prem LLM endpoints only', options:{bullet:true, breakLine:true}},
  {text:'Human approval gate — no network change', options:{bullet:true}},
], {x:CX[0]+0.24, y:CY+0.80, w:CW-0.48, h:1.45, isTextBox:true, margin:0,
    fontFace:F.b, fontSize:10.5, color:C.ink2, paraSpaceAfter:4, lineSpacing:14});

s1.addText('ASSUMED — planning values to validate', {
  x:CX[0]+0.24, y:CY+2.38, w:CW-0.48, h:0.2, isTextBox:true, margin:0,
  fontFace:F.d, fontSize:8.5, bold:true, color:C.rust, charSpacing:0.9});
s1.addText([
  {text:'90% dedup / flap suppression → 700k/day', options:{bullet:true, breakLine:true}},
  {text:'20 events per incident → 35k UAI/day', options:{bullet:true, breakLine:true}},
  {text:'35% of incidents earn a GenAI RFO', options:{bullet:true, breakLine:true}},
  {text:'RFO = 3 turns × 6k in / 400 out tokens', options:{bullet:true, breakLine:true}},
  {text:'Peak hour = 10% of the day → 2.4×', options:{bullet:true, breakLine:true}},
  {text:'8k tickets/day written to HPSM', options:{bullet:true}},
], {x:CX[0]+0.24, y:CY+2.62, w:CW-0.48, h:1.75, isTextBox:true, margin:0,
    fontFace:F.b, fontSize:10.5, color:C.ink2, paraSpaceAfter:4, lineSpacing:14});

s1.addShape(p.ShapeType.roundRect, {x:CX[0]+0.24, y:CY+4.55, w:CW-0.48, h:0.72,
  rectRadius:0.04, fill:{color:C.sunk}, line:{type:'none'}});
s1.addText([
  {text:'Every assumed value is a dial. ', options:{bold:true, color:C.ink}},
  {text:'None of them changes the measured capacity — only how much of it we need.', options:{color:C.ink2}},
], {x:CX[0]+0.38, y:CY+4.64, w:CW-0.76, h:0.55, isTextBox:true, margin:0,
    fontFace:F.b, fontSize:10, lineSpacing:13});

/* ---- col 2 : decision points ---- */
card(s1, CX[1], CY, CW, CH);
sq(s1, CX[1]+0.24, CY+0.28, C.teal);
head(s1, CX[1]+0.40, CY+0.20, CW-0.6, 'DECISION POINTS', C.ink);

const DEC = [
  ['Two serving pools, not one',
   'RFO is throughput-shaped; chat is latency-shaped. One pool forces the interactive SLO onto batch work.', 0.50],
  ['Size on goodput, not peak throughput',
   'Capacity = throughput at the last concurrency whose p95 meets the SLO. A: ≤30 s. B: TTFT ≤1.5 s, ITL ≤25 ms.', 0.50],
  ['Derate to 70% of the knee',
   'Queueing delay grows like ρ/(1−ρ). At the knee, the first burst breaks the SLO.', 0.34],
  ['Model must fit a single GPU',
   '120B MoE at MXFP4 ≈ 62 GB — no TP, failure domain of one GPU. A dense 70B FP8 needs 2×H100.', 0.50],
  ['N+1 per site, two sites',
   'A national NOC platform cannot carry a single-DC dependency. Not token volume — this sets the fleet.', 0.50],
  ['Measure the denominator',
   '11-point GuideLLM sweep at our real token shapes, not a vendor tok/s figure.', 0.34],
];
let dy = CY + 0.58;
DEC.forEach(([t, sub, sh], i) => {
  s1.addText(String(i+1), {x:CX[1]+0.22, y:dy, w:0.26, h:0.22, isTextBox:true, margin:0,
    fontFace:F.m, fontSize:10, bold:true, color:C.teal});
  s1.addText(t, {x:CX[1]+0.52, y:dy-0.015, w:CW-0.78, h:0.22, isTextBox:true, margin:0,
    fontFace:F.d, fontSize:11, bold:true, color:C.ink});
  s1.addText(sub, {x:CX[1]+0.52, y:dy+0.21, w:CW-0.78, h:sh, isTextBox:true, margin:0,
    fontFace:F.b, fontSize:9.5, color:C.ink3, lineSpacing:12});
  dy += 0.21 + sh + 0.16;
});

/* ---- col 3 : parameters ---- */
card(s1, CX[2], CY, CW, CH);
sq(s1, CX[2]+0.24, CY+0.28, C.rust);
head(s1, CX[2]+0.40, CY+0.20, CW-0.6, 'PARAMETERS THAT MOVE IT', C.ink);
s1.addText('Each row moves one dial and leaves the rest at baseline. Production GPUs on the right.', {
  x:CX[2]+0.24, y:CY+0.52, w:CW-0.48, h:0.42, isTextBox:true, margin:0,
  fontFace:F.b, fontSize:9.5, color:C.ink3, lineSpacing:12});

const PAR = [
  ['Baseline as modelled',     1.0,  10, true],
  ['RFO context 6k → 24k',     3.5,  18, false],
  ['Compression misses 3×',    2.8,  16, false],
  ['Every incident gets RFO',  2.6,  16, false],
  ['Agent loop 3 → 6 turns',   1.9,  14, false],
  ['Chat as primary UI',       1.4,  12, false],
  ['Verbose RFO 400 → 1,500',  1.2,  10, false],
  ['Lean: P1/P2 only',         0.4,   8, false],
];
const BX = CX[2]+0.24, BW = CW-0.48;
const labW = 1.72, barX = BX+1.78, barW = 0.86, xX = BX+2.70, gX = BX+3.10, MAXX = 3.5;
s1.addText('× DEMAND', {x:barX, y:CY+1.02, w:1.3, h:0.18, isTextBox:true, margin:0,
  fontFace:F.d, fontSize:7.5, bold:true, color:C.ink3, charSpacing:0.8});
s1.addText('GPU', {x:gX, y:CY+1.02, w:BW-(gX-BX), h:0.18, isTextBox:true, margin:0,
  fontFace:F.d, fontSize:7.5, bold:true, color:C.ink3, charSpacing:0.8, align:'right'});

let py = CY + 1.26;
PAR.forEach(([t, x, g, base]) => {
  s1.addText(t, {x:BX, y:py-0.02, w:labW, h:0.24, isTextBox:true, margin:0,
    fontFace:F.b, fontSize:9.5, bold:base, color: base ? C.ink : C.ink2});
  s1.addShape(p.ShapeType.rect, {x:barX, y:py+0.055, w:barW, h:0.11,
    fill:{color:C.sunk}, line:{type:'none'}});
  s1.addShape(p.ShapeType.rect, {x:barX, y:py+0.055, w:Math.max(0.03, barW*(x/MAXX)), h:0.11,
    fill:{color: base ? C.teal : C.rust}, line:{type:'none'}});
  s1.addText(x.toFixed(1)+'×', {x:xX, y:py-0.02, w:0.38, h:0.24, isTextBox:true,
    margin:0, fontFace:F.m, fontSize:8.5, color:C.ink3});
  s1.addText(String(g), {x:gX, y:py-0.02, w:BW-(gX-BX), h:0.24, isTextBox:true, margin:0,
    fontFace:F.m, fontSize:10, bold:true, color: base ? C.teal : C.ink, align:'right'});
  py += 0.335;
});

s1.addShape(p.ShapeType.roundRect, {x:BX, y:CY+4.10, w:BW, h:1.17, rectRadius:0.04,
  fill:{color:C.sunk}, line:{type:'none'}});
s1.addText('Context length is the dominant lever', {
  x:BX+0.14, y:CY+4.20, w:BW-0.28, h:0.22, isTextBox:true, margin:0,
  fontFace:F.d, fontSize:10, bold:true, color:C.rust});
s1.addText('Prompt size moves total demand more than incident count does. A per-agent context budget therefore belongs in the LLD as a hard constraint, not as a tuning knob adjusted in production.', {
  x:BX+0.14, y:CY+4.44, w:BW-0.28, h:0.78, isTextBox:true, margin:0,
  fontFace:F.b, fontSize:9.5, color:C.ink2, lineSpacing:12});

s1.addNotes('Left: what is fixed by the SoW versus what we assumed. Right: the assumptions ranked by how much they move the answer. Middle: the six engineering decisions. The point of the slide is that capacity was measured and only demand was assumed.');

/* ================================================================ SLIDE 2 */
const s2 = p.addSlide();
s2.background = {color: C.dark};

s2.addText('The answer, and what it rests on', {
  x:M, y:0.36, w:USE, h:0.5, isTextBox:true, margin:0,
  fontFace:F.d, fontSize:29, bold:true, color:C.dink, charSpacing:-0.4});
s2.addText([
  {text:'11-point GuideLLM sweep', options:{color:C.dteal, bold:true}},
  {text:'   ·   two pools × concurrency 1–32   ·   capacity taken at the SLO-passing knee, then derated 30%',
   options:{color:C.dink3}},
], {x:M, y:0.88, w:USE, h:0.28, isTextBox:true, margin:0, fontFace:F.b, fontSize:11.5});

/* --- stat row --- */
const ST = [
  ['14', '× H100 80GB', 'GPU fleet', '10 production over 2 sites,\n2 non-prod, 2 training', true],
  ['488', 'vCPU', 'CPU platform', '4,768 GB RAM ≈ 7 nodes,\nRAM-bound not CPU-bound', false],
  ['43.9', 'TB', 'Storage', '9.2 TB logical ×3 replication\n×1.6 growth, NVMe', false],
  ['268', 'M tok/day', 'Token demand', '98B/year — two of the\nfive agents use tokens', false],
];
const SW = (USE - 0.45)/4;
ST.forEach(([n, u, l, s, hero], i) => {
  const x = M + i*(SW+0.15);
  card(s2, x, 1.30, SW, 1.62, true);
  s2.addText(l.toUpperCase(), {x:x+0.20, y:1.44, w:SW-0.4, h:0.2, isTextBox:true, margin:0,
    fontFace:F.d, fontSize:8.5, bold:true, color:C.dink3, charSpacing:1});
  s2.addText([
    {text:n, options:{fontSize:31, bold:true, color: hero ? C.dteal : C.dink}},
    {text:' '+u, options:{fontSize:11, bold:true, color:C.dink3}},
  ], {x:x+0.20, y:1.66, w:SW-0.4, h:0.56, isTextBox:true, margin:0, fontFace:F.d});
  s2.addText(s, {x:x+0.20, y:2.24, w:SW-0.4, h:0.56, isTextBox:true, margin:0,
    fontFace:F.b, fontSize:9.5, color:C.dink2, lineSpacing:12});
});

/* --- derivation chain --- */
s2.addText('THE DIVISION', {x:M, y:3.10, w:3, h:0.2, isTextBox:true, margin:0,
  fontFace:F.d, fontSize:8.5, bold:true, color:C.dink3, charSpacing:1});
const CHAIN = [
  ['Peak-hour demand', '7,458 tok/s', 'both pools, 2.4× the daily mean'],
  ['Measured capacity', '6,066 / 3,797', 'tok/s per H100 at the SLO knee'],
  ['After 30% headroom', '4,246 / 2,658', 'usable tok/s per H100'],
  ['GPUs actually serving', '1.9 → 3', 'peak-hour requirement'],
  ['Plus N+1, 2 sites, non-prod', '14 × H100', 'HA and DR, not token volume'],
];
const CHW = (USE - 4*0.26)/5;
CHAIN.forEach(([t, v, s], i) => {
  const x = M + i*(CHW+0.26);
  card(s2, x, 3.36, CHW, 1.00, true);
  s2.addText(t, {x:x+0.16, y:3.46, w:CHW-0.32, h:0.2, isTextBox:true, margin:0,
    fontFace:F.b, fontSize:9, color:C.dink3});
  s2.addText(v, {x:x+0.16, y:3.66, w:CHW-0.32, h:0.28, isTextBox:true, margin:0,
    fontFace:F.d, fontSize:15, bold:true, color: i===4 ? C.dteal : C.dink});
  s2.addText(s, {x:x+0.16, y:3.97, w:CHW-0.32, h:0.32, isTextBox:true, margin:0,
    fontFace:F.b, fontSize:8, color:C.dink3, lineSpacing:10});
  if (i < 4) {
    s2.addShape(p.ShapeType.rightArrow, {x:x+CHW+0.055, y:3.79, w:0.15, h:0.14,
      fill:{color:C.drust}, line:{type:'none'}});
  }
});

/* --- three findings --- */
const FIND = [
  ['The LLM tier is the small part',
   'Peak demand needs about two GPUs of serving; average utilisation of the serving fleet is near 20%. The fleet is sized by peak and by HA, never by average load.',
   C.dteal],
  ['The platform is floor-bound',
   '11 of 13 components are sized by their operational floor — JVM heap, compaction, quorum — not by Vi’s event rate. Halving alarm volume does not make this cheaper; only removing components does.',
   C.dteal],
  ['On-prem does not pay for itself',
   '10 H100 ≈ $280k/yr against ≈$59k/yr for the same tokens hosted; break-even is ~4.8× this volume. We build private because the data cannot leave — saying so is what keeps the business case credible.',
   C.drust],
];
const FW = (USE - 0.5)/3;
FIND.forEach(([t, b, c], i) => {
  const x = M + i*(FW+0.25);
  card(s2, x, 4.62, FW, 1.62, true);
  sq(s2, x+0.20, 4.87, c);
  s2.addText(t, {x:x+0.36, y:4.78, w:FW-0.56, h:0.24, isTextBox:true, margin:0,
    fontFace:F.d, fontSize:12, bold:true, color:C.dink});
  s2.addText(b, {x:x+0.20, y:5.10, w:FW-0.4, h:1.06, isTextBox:true, margin:0,
    fontFace:F.b, fontSize:10, color:C.dink2, lineSpacing:13.5});
});

s2.addText([
  {text:'Method:  ', options:{bold:true, color:C.dink}},
  {text:'GuideLLM 0.7.3 measured request rate, latency, TTFT and ITL end to end; per-point TTFT/ITL were pinned to published gpt-oss-120b + vLLM figures for one H100 80GB, since the modelling host has no GPU. Pointing --backend at a live vLLM endpoint re-derives every number above.',
   options:{color:C.dink2}},
], {x:M, y:6.50, w:USE, h:0.42, isTextBox:true, margin:0, fontFace:F.b, fontSize:8.5, lineSpacing:11});

s2.addNotes('Top row is the answer. The chain shows the actual arithmetic: peak demand over derated measured capacity gives about two serving GPUs; everything else is HA, DR, eval and training. The three findings are what to lead with in a review.');

p.writeFile({fileName:'/home/user/Claude/deck/Vi-AI-NOC-Sizing.pptx'})
 .then(f => console.log('wrote', f));
