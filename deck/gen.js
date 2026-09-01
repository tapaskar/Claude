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

s1.addText('How three GPUs was arrived at', {
  x:M, y:0.36, w:USE, h:0.5, isTextBox:true, margin:0,
  fontFace:F.d, fontSize:29, bold:true, color:C.ink, charSpacing:-0.4,
});
s1.addText([
  {text:'Vi AI-NOC · RAN fault management', options:{color:C.teal, bold:true}},
  {text:'   ·   ~2M cells, ~10M alarms/day   ·   16 GuideLLM operating points; demand derived from the SoW',
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
  ['One shared pool, not two',
   'Chat is latency-shaped but only 0.24 GPU of load. Same model, one deployment, priority scheduling.', 0.50],
  ['Size on goodput, not peak throughput',
   'Capacity = throughput at the last concurrency whose p95 meets the SLO. RFO: ≤30 s. Chat: TTFT ≤1.5 s, ITL ≤25 ms.', 0.50],
  ['Three, because of N+1',
   'Peak needs 1.37 GPU. Two would meet the SLO; three is the smallest fleet where a GPU can fail at peak hour and still hold.', 0.50],
  ['Model must fit a single GPU',
   '120B MoE at MXFP4 ≈ 62 GB — no TP, failure domain of one GPU, and 21–30 concurrent 6.4k requests of KV headroom.', 0.50],
  ['Single site, for now',
   'The one real loss. Manual NOC process is the fallback — but that expires when headcount comes out, so fund site 2 before then.', 0.50],
  ['Measure the denominator',
   '16-point GuideLLM sweep, including a mixed-traffic run that validates the shared pool to within 3.8%.', 0.34],
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
const PAR = [
  ['RFO context, tokens',   '6,000',  '9,640',  1.57, true],
  ['Incidents per day',     '35,000', '54,900', 1.57, false],
  ['Share earning an RFO',  '35%',    '55%',    1.57, false],
  ['Agent turns per RFO',   '3',      '4.7',    1.57, false],
];
const SCEN = [
  ['Every incident gets RFO',   '2.63×', '5 GPU', false],
  ['Compression misses 3×',     '2.75×', '5 GPU', false],
  ['RFO context 6k → 24k',      '3.47×', '5 GPU', false],
  ['Agent loop 3 → 6 turns',    '2.00×', '4 GPU', false],
  ['Verbose RFO output',       '1.17×', 'fits',  true],
  ['Chat becomes primary UI',   '1.00×', 'fits',  true],
];
const BX = CX[2]+0.24, BW = CW-0.48;
s1.addText('Three GPUs hold until one of these crosses. Each moves alone, N+1 kept.', {
  x:BX, y:CY+0.52, w:BW, h:0.42, isTextBox:true, margin:0,
  fontFace:F.b, fontSize:9.5, color:C.ink3, lineSpacing:12});

const c1=BX, c2=BX+1.62, c3=BX+2.42;
s1.addText('MODELLED', {x:c2, y:CY+0.98, w:0.78, h:0.18, isTextBox:true, margin:0,
  fontFace:F.d, fontSize:7.5, bold:true, color:C.ink3, charSpacing:0.8, align:'right'});
s1.addText('CEILING', {x:c3, y:CY+0.98, w:BW-(c3-BX), h:0.18, isTextBox:true, margin:0,
  fontFace:F.d, fontSize:7.5, bold:true, color:C.rust, charSpacing:0.8, align:'right'});
let py = CY + 1.22;
PAR.forEach(([t, mod, ceil, h, hot]) => {
  s1.addText(t, {x:c1, y:py, w:1.58, h:0.24, isTextBox:true, margin:0,
    fontFace:F.b, fontSize:9.5, bold:hot, color: hot ? C.ink : C.ink2});
  s1.addText(mod, {x:c2, y:py, w:0.78, h:0.24, isTextBox:true, margin:0,
    fontFace:F.m, fontSize:9, color:C.ink3, align:'right'});
  s1.addText(ceil, {x:c3, y:py, w:BW-(c3-BX), h:0.24, isTextBox:true, margin:0,
    fontFace:F.m, fontSize:10, bold:true, color: hot ? C.rust : C.ink, align:'right'});
  py += 0.28;
});

s1.addText('THE SENSITIVITY CASES, RE-RUN AGAINST 3 GPUs', {
  x:BX, y:py+0.14, w:BW, h:0.2, isTextBox:true, margin:0,
  fontFace:F.d, fontSize:7.5, bold:true, color:C.ink3, charSpacing:0.8});
py += 0.40;
SCEN.forEach(([t, mult, need, ok]) => {
  s1.addShape(p.ShapeType.rect, {x:BX, y:py+0.075, w:0.07, h:0.07,
    fill:{color: ok ? C.teal : C.rust}, line:{type:'none'}});
  s1.addText(t, {x:BX+0.18, y:py, w:1.62, h:0.24, isTextBox:true, margin:0,
    fontFace:F.b, fontSize:9.5, color:C.ink2});
  s1.addText(mult, {x:c2, y:py, w:0.78, h:0.24, isTextBox:true, margin:0,
    fontFace:F.m, fontSize:9, color:C.ink3, align:'right'});
  s1.addText(need, {x:c3, y:py, w:BW-(c3-BX), h:0.24, isTextBox:true, margin:0,
    fontFace:F.m, fontSize:9.5, bold:true, color: ok ? C.teal : C.rust, align:'right'});
  py += 0.26;
});

s1.addShape(p.ShapeType.roundRect, {x:BX, y:CY+4.38, w:BW, h:1.05, rectRadius:0.04,
  fill:{color:C.sunk}, line:{type:'none'}});
s1.addText('The context budget is now load-bearing', {
  x:BX+0.14, y:CY+4.48, w:BW-0.28, h:0.22, isTextBox:true, margin:0,
  fontFace:F.d, fontSize:10, bold:true, color:C.rust});
s1.addText('At 14 GPUs a context cap was good practice. At three it is the control: a hard limit in code, with an alert at 8,000 tokens.', {
  x:BX+0.14, y:CY+4.72, w:BW-0.28, h:0.64, isTextBox:true, margin:0,
  fontFace:F.b, fontSize:9.5, color:C.ink2, lineSpacing:12});

s1.addNotes('Left: what the SoW fixes versus what we assumed. Middle: the six decisions the 3-GPU constraint forced. Right: the ceiling on each assumption before a fourth GPU is needed, and the sensitivity cases re-run against three. The point is that capacity was measured and only demand was assumed.');

/* ================================================================ SLIDE 2 */
const s2 = p.addSlide();
s2.background = {color: C.dark};

s2.addText('Three H100 — and what it costs', {
  x:M, y:0.36, w:USE, h:0.5, isTextBox:true, margin:0,
  fontFace:F.d, fontSize:29, bold:true, color:C.dink, charSpacing:-0.4});
s2.addText([
  {text:'Peak-hour demand measures 1.37 GPU of work', options:{color:C.dteal, bold:true}},
  {text:'   ·   three carries it with N+1   ·   two independent methods agree to within 3.8%',
   options:{color:C.dink3}},
], {x:M, y:0.88, w:USE, h:0.28, isTextBox:true, margin:0, fontFace:F.b, fontSize:11.5});

/* --- stat row --- */
const ST = [
  ['3', '× H100 80GB', 'GPU fleet', 'One shared pool, single site.\nN+1 across the platform.', true],
  ['46', '% at peak', 'Utilisation', '69% with one GPU down;\n19% at average load.', false],
  ['1.6', '× headroom', 'Growth', 'RFO demand can grow 57%\nbefore a 4th GPU.', false],
  ['308', 'k $/year', 'Saving', 'vs the 14-GPU two-site\ndesign, on GPU alone.', false],
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
  ['Peak-hour demand', '7,458 tok/s', 'both classes, 2.4× the daily mean'],
  ['Shared-pool capacity', '5,433 tok/s', 'measured, mixed traffic, per H100'],
  ['Work required', '1.37 GPU', 'additive method agrees to 3.8%'],
  ['Survives one failure', '68.6%', 'of capacity on the 2 that remain'],
  ['Fleet', '3 × H100', 'the smallest N+1 that holds'],
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
  ['Three is an HA number, not throughput',
   'Peak needs 1.37 GPU, so two would meet the SLO. Three is the smallest fleet where a GPU can fail during the busiest hour and the platform still holds. That is the whole case for the third card.',
   C.dteal],
  ['Chat was only 0.24 GPU of load',
   'Two pools was the right architecture and the wrong sizing. Same model, one deployment, priority scheduling. The one thing arithmetic cannot settle — interactive TTFT under long prefills — is a day on a rented card.',
   C.dteal],
  ['Single site is the one real loss',
   'Everything else dropped was over-provisioning. The manual NOC process covers a DC outage today, but that expires when headcount comes out — so fund site 2 before the reduction lands, not after.',
   C.drust],
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
  {text:'16 GuideLLM operating points across three workload profiles, including a shared-pool run driven from two simultaneous data sources so the scheduler sees real mixed traffic. Per-point TTFT/ITL were pinned to published gpt-oss-120b + vLLM figures for one H100 80GB, since the modelling host has no GPU. Pointing --backend at a live vLLM endpoint re-derives every number above.',
   options:{color:C.dink2}},
], {x:M, y:6.70, w:USE, h:0.42, isTextBox:true, margin:0, fontFace:F.b, fontSize:8.5, lineSpacing:11});

s2.addNotes('Top row is the answer. The chain is the arithmetic: peak demand over measured shared-pool capacity is 1.37 GPU; three is what N+1 costs. Lead with the three findings — especially the last one, since single site is the only genuine risk in the descope and it has an expiry date.');

p.writeFile({fileName:'/home/user/Claude/deck/Vi-AI-NOC-Sizing.pptx'})
 .then(f => console.log('wrote', f));
