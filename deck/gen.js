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

s1.addText('Sizing FM + Change Management', {
  x:M, y:0.36, w:USE, h:0.5, isTextBox:true, margin:0,
  fontFace:F.d, fontSize:29, bold:true, color:C.ink, charSpacing:-0.4,
});
s1.addText([
  {text:'Vi Network AI Platform', options:{color:C.teal, bold:true}},
  {text:'   ·   per the IBM SNOC TSD (20-08-26)   ·   15M alarms/day, H200 141GB, 3 model tiers',
   options:{color:C.ink3}},
], {x:M, y:0.88, w:USE, h:0.28, isTextBox:true, margin:0, fontFace:F.b, fontSize:11.5});

const CY = 1.42, CH = 5.5, CW = (USE - 0.6)/3;
const CX = [M, M+CW+0.3, M+2*(CW+0.3)];

/* ---- col 1 : assumptions ---- */
card(s1, CX[0], CY, CW, CH);
sq(s1, CX[0]+0.24, CY+0.28, C.teal);
head(s1, CX[0]+0.40, CY+0.20, CW-0.6, 'ASSUMPTIONS', C.ink);

s1.addText('FIXED — stated in the TSD', {
  x:CX[0]+0.24, y:CY+0.56, w:CW-0.48, h:0.2, isTextBox:true, margin:0,
  fontFace:F.d, fontSize:8.5, bold:true, color:C.teal, charSpacing:0.9});
s1.addText([
  {text:'15M alarms/day, 1M-node topology graph  (§12)', options:{bullet:true, breakLine:true}},
  {text:'52k batch / 5 min; 500k burst in <180 s  (§12)', options:{bullet:true, breakLine:true}},
  {text:'H200 141GB, FP8 / MXFP4 on vLLM  (§12, §3.7)', options:{bullet:true, breakLine:true}},
  {text:'6 model tiers incl. VLM + E5  (§3.4.6, §3.7)', options:{bullet:true, breakLine:true}},
  {text:'8 CHM agents, GUJ first → pan-India  (§6.8–6.13)', options:{bullet:true, breakLine:true}},
  {text:'Release docs quarterly / bi-annual  (§5.1)', options:{bullet:true, breakLine:true}},
  {text:'Max 5 concurrent changes per circle  (§6.11)', options:{bullet:true}},
], {x:CX[0]+0.24, y:CY+0.80, w:CW-0.48, h:2.10, isTextBox:true, margin:0,
    fontFace:F.b, fontSize:10, color:C.ink2, paraSpaceAfter:3, lineSpacing:13});

s1.addText('ASSUMED — planning values to validate', {
  x:CX[0]+0.24, y:CY+2.98, w:CW-0.48, h:0.2, isTextBox:true, margin:0,
  fontFace:F.d, fontSize:8.5, bold:true, color:C.rust, charSpacing:0.9});
s1.addText([
  {text:'70% RAN-linked → 52.5k incidents/day', options:{bullet:true, breakLine:true}},
  {text:'35% of incidents earn a GenAI RFO', options:{bullet:true, breakLine:true}},
  {text:'RFO = 3 turns × 6k in / 400 out tokens', options:{bullet:true, breakLine:true}},
  {text:'CHM: 100 CRs/day GUJ → 1,250 pan-India', options:{bullet:true, breakLine:true}},
  {text:'Release drop = 12 docs GUJ → 150 national', options:{bullet:true, breakLine:true}},
  {text:'Peak hour = 10% of the day → 2.4×', options:{bullet:true}},
], {x:CX[0]+0.24, y:CY+3.22, w:CW-0.48, h:1.40, isTextBox:true, margin:0,
    fontFace:F.b, fontSize:10, color:C.ink2, paraSpaceAfter:3, lineSpacing:13});

s1.addShape(p.ShapeType.roundRect, {x:CX[0]+0.24, y:CY+4.55, w:CW-0.48, h:0.78,
  rectRadius:0.04, fill:{color:C.sunk}, line:{type:'none'}});
s1.addText([
  {text:'Alarms moved 10M → 15M/day. ', options:{bold:true, color:C.ink}},
  {text:'The TSD supersedes the August one-slide. That +50% is what pushes the heavy tier to 2.06 GPU.', options:{color:C.ink2}},
], {x:CX[0]+0.38, y:CY+4.64, w:CW-0.76, h:0.62, isTextBox:true, margin:0,
    fontFace:F.b, fontSize:10, lineSpacing:13});

/* ---- col 2 : decision points ---- */
card(s1, CX[1], CY, CW, CH);
sq(s1, CX[1]+0.24, CY+0.28, C.teal);
head(s1, CX[1]+0.40, CY+0.20, CW-0.6, 'DECISION POINTS', C.ink);

const DEC = [
  ['Route by tier, not by agent',
   'The TSD already tiers: 120b for reasoning, Gemma for extraction, Llama 8B for MOPs. Size each, then add fractions.', 0.50],
  ['One SLO gate per tier',
   'Heavy: latency ≤30 s. Fast: TTFT ≤1.5 s, ITL ≤25 ms. MOP: ≤120 s — batch, it only has to land in the change window.', 0.50],
  ['Size for the target, not phase 1',
   'FM is pan-India from day one; CHM is GUJ first, pan-India after. The pool is bought once, so it is sized on the target state.', 0.50],
  ['Treat MOP generation as a burst',
   'Release docs are quarterly (§5.1): 150 docs → 2,250 MOPs in one window. A daily mean hides the only CHM spike.', 0.50],
  ['Co-locate E5, do not dedicate it',
   'A 0.7 GB encoder at 0.03% utilisation does not need a 141 GB card. Freeing it makes all four cards heavy-capable.', 0.50],
  ['Measure on H200, not H100',
   '4.8 TB/s vs 3.35 — decode is bandwidth-bound, so ITL improves ~1.43×. Capacity is 7,008 tok/s, not 6,066.', 0.50],
];
let dy = CY + 0.58;
DEC.forEach(([t, sub, sh], i) => {
  s1.addText(String(i+1), {x:CX[1]+0.22, y:dy, w:0.26, h:0.22, isTextBox:true, margin:0,
    fontFace:F.m, fontSize:10, bold:true, color:C.teal});
  s1.addText(t, {x:CX[1]+0.52, y:dy-0.015, w:CW-0.78, h:0.22, isTextBox:true, margin:0,
    fontFace:F.d, fontSize:11, bold:true, color:C.ink});
  s1.addText(sub, {x:CX[1]+0.52, y:dy+0.21, w:CW-0.78, h:sh, isTextBox:true, margin:0,
    fontFace:F.b, fontSize:9.5, color:C.ink3, lineSpacing:12});
  dy += 0.21 + sh + 0.12;
});

/* ---- col 3 : parameters ---- */
card(s1, CX[2], CY, CW, CH);
sq(s1, CX[2]+0.24, CY+0.28, C.rust);
head(s1, CX[2]+0.40, CY+0.20, CW-0.6, 'PARAMETERS THAT MOVE IT', C.ink);
const PAR = [
  ['heavy · gpt-oss-120b', '6k/400',  '7,008',  '2.06', true],
  ['fast · Gemma 4 26B',   '1.5k/200','20,936', '0.16', false],
  ['mop · Llama 3.1 8B',   '12k/2.5k','7,733',  '0.17', false],
];
const SCEN = [
  ['FM · pan-India',        '398M', '82%', false],
  ['CHM · pan-India',        '86M', '18%', true],
  ['CHM · Gujarat only',    '7.3M', '1.8%', true],
];
const BX = CX[2]+0.24, BW = CW-0.48;
s1.addText('Measured on one H200 141GB, gated per tier. GPU column is what pan-India peak demand needs.', {
  x:BX, y:CY+0.52, w:BW, h:0.42, isTextBox:true, margin:0,
  fontFace:F.b, fontSize:9.5, color:C.ink3, lineSpacing:12});

const c1=BX, c2=BX+1.42, c3=BX+2.12, c4=BX+2.92;
s1.addText('SHAPE',  {x:c2, y:CY+0.98, w:0.66, h:0.18, isTextBox:true, margin:0,
  fontFace:F.d, fontSize:7.5, bold:true, color:C.ink3, charSpacing:0.8, align:'right'});
s1.addText('TOK/S',  {x:c3, y:CY+0.98, w:0.76, h:0.18, isTextBox:true, margin:0,
  fontFace:F.d, fontSize:7.5, bold:true, color:C.ink3, charSpacing:0.8, align:'right'});
s1.addText('GPU',    {x:c4, y:CY+0.98, w:BW-(c4-BX), h:0.18, isTextBox:true, margin:0,
  fontFace:F.d, fontSize:7.5, bold:true, color:C.rust, charSpacing:0.8, align:'right'});
let py = CY + 1.22;
PAR.forEach(([t, shape, tok, gpu, hot]) => {
  s1.addText(t, {x:c1, y:py, w:1.38, h:0.24, isTextBox:true, margin:0,
    fontFace:F.b, fontSize:9.5, bold:hot, color: hot ? C.ink : C.ink2});
  s1.addText(shape, {x:c2, y:py, w:0.66, h:0.24, isTextBox:true, margin:0,
    fontFace:F.m, fontSize:8.5, color:C.ink3, align:'right'});
  s1.addText(tok, {x:c3, y:py, w:0.76, h:0.24, isTextBox:true, margin:0,
    fontFace:F.m, fontSize:9.5, color:C.ink2, align:'right'});
  s1.addText(gpu, {x:c4, y:py, w:BW-(c4-BX), h:0.24, isTextBox:true, margin:0,
    fontFace:F.m, fontSize:10, bold:true, color: hot ? C.rust : C.ink, align:'right'});
  py += 0.30;
});
s1.addShape(p.ShapeType.line, {x:BX, y:py+0.06, w:BW, h:0,
  line:{color:C.rule, width:0.75}});
s1.addText('TOTAL at pan-India peak', {x:c1, y:py+0.12, w:2.4, h:0.24, isTextBox:true,
  margin:0, fontFace:F.b, fontSize:9.5, bold:true, color:C.ink});
s1.addText('2.40', {x:c4, y:py+0.12, w:BW-(c4-BX), h:0.24, isTextBox:true, margin:0,
  fontFace:F.m, fontSize:10, bold:true, color:C.teal, align:'right'});
py += 0.52;

s1.addText('WHERE THE TOKENS COME FROM', {x:BX, y:py+0.10, w:BW, h:0.2, isTextBox:true,
  margin:0, fontFace:F.d, fontSize:7.5, bold:true, color:C.ink3, charSpacing:0.8});
py += 0.36;
SCEN.forEach(([t, tok, pct, isChm]) => {
  s1.addShape(p.ShapeType.rect, {x:BX, y:py+0.075, w:0.07, h:0.07,
    fill:{color: isChm ? C.rust : C.teal}, line:{type:'none'}});
  s1.addText(t, {x:BX+0.18, y:py, w:1.9, h:0.24, isTextBox:true, margin:0,
    fontFace:F.b, fontSize:9.5, color:C.ink2});
  s1.addText(tok, {x:c3, y:py, w:0.76, h:0.24, isTextBox:true, margin:0,
    fontFace:F.m, fontSize:9, color:C.ink3, align:'right'});
  s1.addText(pct, {x:c4, y:py, w:BW-(c4-BX), h:0.24, isTextBox:true, margin:0,
    fontFace:F.m, fontSize:9.5, bold:true, color: isChm ? C.rust : C.ink, align:'right'});
  py += 0.28;
});

s1.addShape(p.ShapeType.roundRect, {x:BX, y:CY+4.42, w:BW, h:1.00, rectRadius:0.04,
  fill:{color:C.sunk}, line:{type:'none'}});
s1.addText('CHM does not move the number', {
  x:BX+0.14, y:CY+4.52, w:BW-0.28, h:0.22, isTextBox:true, margin:0,
  fontFace:F.d, fontSize:10, bold:true, color:C.rust});
s1.addText('Even pan-India it is 18% of tokens and 0.33 of a GPU. The alarm tier at 15M/day sets the fleet; CHM adds model tiers, not cards.', {
  x:BX+0.14, y:CY+4.76, w:BW-0.28, h:0.60, isTextBox:true, margin:0,
  fontFace:F.b, fontSize:9.5, color:C.ink2, lineSpacing:12});

s1.addNotes('Left: what the IBM TSD fixes versus what we assumed — note alarms moved from 10M to 15M/day, which is what drives the heavy tier. Middle: the six sizing decisions. Right: measured capacity per model tier on H200, and where the tokens actually come from. The headline of this slide is that Change Management adds model tiers, not GPUs.');

/* ================================================================ SLIDE 2 */
const s2 = p.addSlide();
s2.background = {color: C.dark};

s2.addText('The TSD pool: right total, wrong split', {
  x:M, y:0.36, w:USE, h:0.5, isTextBox:true, margin:0,
  fontFace:F.d, fontSize:29, bold:true, color:C.dink, charSpacing:-0.4});
s2.addText([
  {text:'Measured demand lands on the TSD\u2019s own 4 production H200', options:{color:C.dteal, bold:true}},
  {text:'   ·   but the heavy tier needs 2.06 of them, so \u201c2 active for HA\u201d has no headroom left',
   options:{color:C.dink3}},
], {x:M, y:0.88, w:USE, h:0.28, isTextBox:true, margin:0, fontFace:F.b, fontSize:11.5});

/* --- stat row --- */
const ST = [
  ['4', '+1 × H200', 'Production GPU', 'Matches the TSD total.\n3 serving + 1 for N+1.', true],
  ['2.06', 'of 3 cards', 'Heavy tier', 'gpt-oss-120b alone, at\npan-India peak.', false],
  ['18', '% of tokens', 'Change Mgmt', 'Pan-India, on a release\nburst day. 0.33 GPU.', false],
  ['0.03', '% utilised', 'The E5 card', 'A 0.7 GB encoder on a\n141 GB card.', false],
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
s2.addText('HA POSTURE AT PAN-INDIA PEAK', {x:M, y:3.10, w:4, h:0.2, isTextBox:true, margin:0,
  fontFace:F.d, fontSize:8.5, bold:true, color:C.dink3, charSpacing:1});
const CHAIN = [
  ['3 cards healthy', '48% of knee', 'comfortable — the normal state'],
  ['2 active (TSD HA)', '72% of knee', 'meets SLO, 30% headroom spent'],
  ['1 surviving', '145% of knee', 'SLO breach at peak hour'],
  ['Free the E5 card', '4 heavy-capable', 'turns 2-at-the-edge into 3-with-margin'],
  ['Model tiers covered', '2 of 6', 'Gemma, Llama 8B and the VLM have no node'],
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
  if (i < 2) {
    s2.addShape(p.ShapeType.rightArrow, {x:x+CHW+0.055, y:3.79, w:0.15, h:0.14,
      fill:{color:C.drust}, line:{type:'none'}});
  }
});

/* --- three findings --- */
const FIND = [
  ['CHM adds tiers, not cards',
   'Pan-India CHM is 18% of tokens and 0.33 of a GPU. What it really adds is two more model tiers to host — Llama 3.1 8B for MOP generation and heavier use of the Gemma fast tier — neither of which has a node in the §12 pool.',
   C.dteal],
  ['The §12 pool covers 2 of 6 models',
   'It allocates nodes for gpt-oss-120b and E5. Gemma 4 26B, Gemma 4 E4B, Llama 3.1 8B and the VLM are named elsewhere in the TSD with no allocation. Weights co-reside in 107 of 141 GB — but compute does not.',
   C.drust],
  ['Reallocate rather than buy more',
   'E5 runs at 0.03% of one card. Co-locate it with the fast tier and all four cards become heavy-capable — the same spend, but three active at peak instead of two at the edge.',
   C.dteal],
];
const FW = (USE - 0.5)/3;
FIND.forEach(([t, b, c], i) => {
  const x = M + i*(FW+0.25);
  card(s2, x, 4.62, FW, 1.86, true);
  sq(s2, x+0.20, 4.87, c);
  s2.addText(t, {x:x+0.36, y:4.78, w:FW-0.56, h:0.24, isTextBox:true, margin:0,
    fontFace:F.d, fontSize:12, bold:true, color:C.dink});
  s2.addText(b, {x:x+0.20, y:5.10, w:FW-0.4, h:1.30, isTextBox:true, margin:0,
    fontFace:F.b, fontSize:10, color:C.dink2, lineSpacing:13.5});
});

s2.addText([
  {text:'Method:  ', options:{bold:true, color:C.dink}},
  {text:'13 GuideLLM operating points across the three model tiers the TSD names, calibrated to H200 141GB (4.8 TB/s — decode ~1.43\u00d7 an H100, prefill held flat). Volumes are the TSD\u2019s own: 15M alarms/day, 8 CHM agents, Gujarat in phase 1 and pan-India at target. The one thing arithmetic cannot settle is co-resident compute — that needs a run on the real card.',
   options:{color:C.dink2}},
], {x:M, y:6.70, w:USE, h:0.42, isTextBox:true, margin:0, fontFace:F.b, fontSize:8.5, lineSpacing:11});

s2.addNotes('The total in the TSD is right — 4 production H200 — and my independent measured model lands on the same number. The issue is the split: 3 cards for gpt-oss-120b and 1 dedicated to E5 leaves the heavy tier at 2.06 of 3, so the stated 2-active HA posture has no headroom. Freeing the E5 card fixes it at zero extra cost. Lead with the middle finding in a design review: four of the six model tiers the document describes have no node allocated.');

p.writeFile({fileName:'/home/user/Claude/deck/Vi-AI-NOC-Sizing.pptx'})
 .then(f => console.log('wrote', f));
