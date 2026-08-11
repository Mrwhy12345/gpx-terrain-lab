"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type RouteFacts = { name: string; points: number; distanceKm: number };

const baseline = {
  objectSize: 100,
  resolution: 8,
  elevationScale: 1.8,
  pathThickness: 1.6,
  pathScale: 0.8,
  riverWidth: 1,
  waterThreshold: 1,
};

function haversine(a: [number, number], b: [number, number]) {
  const r = 6371;
  const rad = Math.PI / 180;
  const dLat = (b[1] - a[1]) * rad;
  const dLon = (b[0] - a[0]) * rad;
  const q = Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * rad) * Math.cos(b[1] * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(q));
}

function TerrainCanvas({ routeReady }: { routeReady: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    const box = canvas.getBoundingClientRect();
    canvas.width = box.width * dpr;
    canvas.height = box.height * dpr;
    ctx.scale(dpr, dpr);
    const w = box.width, h = box.height;
    ctx.clearRect(0, 0, w, h);
    ctx.save();
    ctx.translate(w / 2, h / 2 + 6);
    ctx.beginPath();
    for (let i = 0; i < 6; i++) {
      const a = Math.PI / 3 * i;
      const x = Math.cos(a) * Math.min(w * .39, 240);
      const y = Math.sin(a) * Math.min(h * .42, 180);
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    }
    ctx.closePath(); ctx.clip();
    const g = ctx.createLinearGradient(0, -180, 0, 190);
    g.addColorStop(0, "#90979b"); g.addColorStop(.26, "#765438"); g.addColorStop(.49, "#506f3e"); g.addColorStop(1, "#284c35");
    ctx.fillStyle = g; ctx.fillRect(-w / 2, -h / 2, w, h);
    for (let y = -170; y < 180; y += 9) {
      ctx.beginPath();
      for (let x = -250; x <= 250; x += 5) {
        const yy = y + Math.sin(x * .065 + y * .025) * 8 + Math.cos(x * .018 - y * .05) * 5;
        x === -250 ? ctx.moveTo(x, yy) : ctx.lineTo(x, yy);
      }
      ctx.strokeStyle = "rgba(237,245,223,.16)"; ctx.lineWidth = 1; ctx.stroke();
    }
    const river = [[-185,95],[-120,65],[-75,80],[-15,48],[35,70],[70,30],[105,22],[140,-5],[180,-55]];
    ctx.beginPath(); river.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));
    ctx.strokeStyle="#2f74c8"; ctx.lineWidth=5; ctx.lineCap="round"; ctx.lineJoin="round"; ctx.stroke();
    if (routeReady) {
      const trail=[[-145,-90],[-120,-35],[-88,5],[-40,35],[15,60],[56,48],[92,10],[72,-30],[110,-70]];
      ctx.beginPath(); trail.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));
      ctx.strokeStyle="#db3f31"; ctx.lineWidth=7; ctx.lineCap="round"; ctx.lineJoin="round"; ctx.stroke();
      ctx.fillStyle="#db3f31"; ctx.beginPath(); ctx.arc(-145,-90,7,0,Math.PI*2); ctx.fill();
      ctx.lineWidth=4; ctx.beginPath(); ctx.arc(110,-70,10,0,Math.PI*2); ctx.stroke();
      ctx.beginPath(); ctx.arc(110,-70,3,0,Math.PI*2); ctx.fill();
    }
    ctx.restore();
  }, [routeReady]);
  return <canvas ref={ref} className="terrain-canvas" aria-label="沙盘效果示意" />;
}

export default function Home() {
  const [facts, setFacts] = useState<RouteFacts | null>(null);
  const [title, setTitle] = useState("星溪竹林");
  const [date, setDate] = useState("2026-07-12");
  const [size, setSize] = useState(100);
  const [resolution, setResolution] = useState(8);
  const [elevation, setElevation] = useState(1.8);
  const [pathWidth, setPathWidth] = useState(1.6);
  const [water, setWater] = useState(true);
  const [forest, setForest] = useState(false);
  const [city, setCity] = useState(false);
  const deviations = [size !== 100, resolution !== 8, elevation !== 1.8, pathWidth !== 1.6].filter(Boolean).length;
  const outputName = title.trim() || facts?.name || "徒步路线";
  const job = useMemo(() => ({
    schema_version: "1.1-web",
    route: { name: outputName, gpx: facts?.name || null },
    customer_input: { display_date: date, title: outputName },
    engineering: {
      source: "TrailPrint3D",
      shape: "HEXAGON", object_size_mm: size, terrain_resolution: resolution,
      elevation_scale: elevation, path_thickness_mm: pathWidth, path_scale: .8,
      element_mode: "SINGLECOLORMODE_REMESH",
      trailprint_water: { water, big_rivers: water, small_rivers: water, include_ocean: water, river_width: 1, water_threshold: 1, min_island_area: 2, coastline_simplify: .1 },
      trailprint_elements: { forests: forest, forest_threshold: 10, city_boundaries: city, city_threshold: 1 },
      bambu: { colors: ["#3F8E43", "#6F5034", "#858C91", "#7A4A20", "#D93025", "#2563B8"], outputs_3mf: 5, outputs_blend: 1 }
    }
  }), [outputName, facts, date, size, resolution, elevation, pathWidth, water, forest, city]);

  async function readGpx(file?: File) {
    if (!file) return;
    const xml = new DOMParser().parseFromString(await file.text(), "application/xml");
    const nodes = Array.from(xml.getElementsByTagNameNS("*", "trkpt"));
    const pts = nodes.map(n => [Number(n.getAttribute("lon")), Number(n.getAttribute("lat"))] as [number, number]);
    const distance = pts.slice(1).reduce((sum, p, i) => sum + haversine(pts[i], p), 0);
    setFacts({ name: file.name, points: pts.length, distanceKm: distance });
    if (!title) setTitle(file.name.replace(/\.gpx$/i, ""));
  }
  function downloadJob() {
    const blob = new Blob([JSON.stringify(job, null, 2)], { type: "application/json" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "job.json"; a.click(); URL.revokeObjectURL(a.href);
  }

  return <main>
    <header className="topbar">
      <div className="brand"><span className="brand-mark">⌁</span><div><strong>GPX Terrain Lab</strong><small>本地徒步沙盘工作台</small></div></div>
      <nav aria-label="制作步骤"><span className="active">01 输入</span><span>02 工程</span><span>03 创意</span><span>04 输出</span></nav>
      <div className="local-pill"><i /> 本地模式 · 数据不离开电脑</div>
    </header>

    <section className="hero-grid">
      <div className="intro">
        <p className="eyebrow">TRAILPRINT3D → BAMBU STUDIO</p>
        <h1>把一条轨迹，<br/><em>变成可触摸的山河。</em></h1>
        <p className="lead">上传 GPX，使用真机验证参数生成地形、水网、轨迹与奖牌框底座。一次配置，交付 5 个 3MF 和 1 个 Blender 项目。</p>
        <label className="upload-card">
          <input type="file" accept=".gpx,application/gpx+xml" onChange={e=>readGpx(e.target.files?.[0])}/>
          <span className="upload-icon">＋</span>
          <span><b>{facts ? facts.name : "拖入或选择 GPX 文件"}</b><small>{facts ? `${facts.points} 个轨迹点 · ${facts.distanceKm.toFixed(2)} km` : "文件只在本机读取，不会上传"}</small></span>
          <strong>{facts ? "已读取" : "选择文件"}</strong>
        </label>
        <div className="trust-row"><span>✓ TrailPrint3D 原生数据</span><span>✓ Bambu 多色适配</span><span>✓ 可断点复用</span></div>
      </div>

      <div className="preview-card">
        <div className="preview-head"><div><span>实时设计预览</span><b>{outputName}</b></div><span className="status-dot">● 参数已同步</span></div>
        <TerrainCanvas routeReady={!!facts}/>
        <div className="legend"><span><i className="green"/>地形</span><span><i className="brown"/>山体</span><span><i className="blue"/>水系</span><span><i className="red"/>轨迹</span></div>
        <div className="model-meta"><div><small>模型尺寸</small><b>{size} mm</b></div><div><small>地形精度</small><b>R{resolution}</b></div><div><small>输出零件</small><b>5 + 1</b></div></div>
      </div>
    </section>

    <section className="workspace">
      <div className="section-title"><div><span>参数工作台</span><h2>从真机基线开始，只调整必要的部分</h2></div><button className="ghost" onClick={()=>{setSize(100);setResolution(8);setElevation(1.8);setPathWidth(1.6)}}>↺ 恢复真机参数</button></div>
      <div className="panel-grid">
        <article className="panel"><div className="panel-no">01</div><h3>作品信息</h3><label>徒步标题<input value={title} onChange={e=>setTitle(e.target.value)}/></label><label>展示日期<input type="date" value={date} onChange={e=>setDate(e.target.value)}/></label><div className="mini-note">标题与底部 Logo 将在创意阶段保持同一主题。</div></article>
        <article className="panel"><div className="panel-no">02</div><h3>地形与轨迹</h3><Param label="模型尺寸" value={size} set={setSize} min={80} max={180} step={5} unit="mm"/><Param label="Resolution" value={resolution} set={setResolution} min={4} max={10} step={1}/><Param label="高程倍率" value={elevation} set={setElevation} min={1} max={3} step={.1}/><Param label="轨迹宽度" value={pathWidth} set={setPathWidth} min={1} max={2.4} step={.1} unit="mm"/></article>
        <article className="panel"><div className="panel-no">03</div><h3>TrailPrint3D 元素</h3><Toggle label="完整水网" detail="湖泊 · 大河 · 小河 · 海岸" value={water} set={setWater}/><Toggle label="森林" detail="Threshold 10.00" value={forest} set={setForest}/><Toggle label="城市边界" detail="Threshold 1.00" value={city} set={setCity}/><div className="source-stamp">数据源固定为 TrailPrint3D</div></article>
        <article className="panel output-panel"><div className="panel-no">04</div><h3>Bambu 输出</h3><ul><li><b>01</b> 三色沙盘地形 <span>绿 · 棕 · 灰</span></li><li><b>02</b> 奖牌框适配底座 <span>灰 · 棕</span></li><li><b>03</b> 徒步轨迹 <span>红</span></li><li><b>04</b> 原生完整水网 <span>蓝</span></li><li><b>05</b> 四件同盘 <span>6 色槽位</span></li><li><b>06</b> Blender 设计预览 <span>.blend</span></li></ul></article>
      </div>
      <div className="action-bar"><div><span className={deviations ? "warn" : "pass"}>{deviations ? `! ${deviations} 项偏离真机基线` : "✓ 真机基线一致"}</span><small>生成前还会检查 Z 轴、非流形边、打印盘范围和奖牌框公差。</small></div><button onClick={downloadJob} disabled={!facts}>导出任务配置 <span>→</span></button></div>
    </section>
    <footer><span>GPX Terrain Lab · 荣耀大地五人组</span><span>TrailPrint3D 获取事实 · Blender 构建 · Bambu Studio 打印</span></footer>
  </main>;
}

function Param({label,value,set,min,max,step,unit=""}:{label:string;value:number;set:(v:number)=>void;min:number;max:number;step:number;unit?:string}) {
  return <label className="param"><span>{label}<b>{value.toFixed(step < 1 ? 2 : 0)} {unit}</b></span><input type="range" min={min} max={max} step={step} value={value} onChange={e=>set(Number(e.target.value))}/></label>
}
function Toggle({label,detail,value,set}:{label:string;detail:string;value:boolean;set:(v:boolean)=>void}) {
  return <label className="toggle-row"><span><b>{label}</b><small>{detail}</small></span><input type="checkbox" checked={value} onChange={e=>set(e.target.checked)}/><i/></label>
}
