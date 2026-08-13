#!/usr/bin/env python3
"""Run repeatable end-to-end audits against GPX-derived Web deliverables."""
from __future__ import annotations

import argparse, hashlib, json, subprocess, sys, xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]; TOOLS=Path(__file__).resolve().parent
JOBS=ROOT/"08_Jobs"; BLENDER=Path("/Applications/Blender.app/Contents/MacOS/Blender")


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def gpx_facts(path):
    root=ET.parse(path).getroot(); segments=[]
    for segment in root.iter():
        if segment.tag.rsplit("}",1)[-1]=="trkseg": segments.append(sum(child.tag.rsplit("}",1)[-1]=="trkpt" for child in segment))
    return {"sha256":sha(path),"track_segments":len(segments),"points":sum(segments),"points_per_segment":segments}


def latest_job(input_hash):
    matches=[]
    for job in JOBS.glob("WEB_*"):
        config=job/"job.json"
        if not config.exists(): continue
        try: data=json.loads(config.read_text(encoding="utf-8"))
        except Exception: continue
        if data.get("input_sha256")==input_hash and len(list((job/"final").glob("*.3mf")))==5 and len(list((job/"final").glob("*.blend")))==1: matches.append(job)
    if not matches: raise RuntimeError(f"No completed Web job matches GPX SHA-256 {input_hash}")
    return sorted(matches)[-1]


def run(command, log):
    result=subprocess.run(command,cwd=ROOT,text=True,capture_output=True)
    log.parent.mkdir(parents=True,exist_ok=True); log.write_text(result.stdout+"\n"+result.stderr,encoding="utf-8")
    if result.returncode: raise RuntimeError(f"Command failed; see {log}")
    return result.stdout.strip()


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("gpx",nargs="+",type=Path); parser.add_argument("--output",type=Path,default=ROOT/"00_Project"/"回归测试")
    args=parser.parse_args(); stamp=datetime.now().strftime("%Y%m%d_%H%M%S"); out=args.output/f"三路线全面回归_{stamp}"; out.mkdir(parents=True,exist_ok=False)
    routes=[]
    for index,gpx in enumerate(args.gpx,1):
        facts=gpx_facts(gpx); job=latest_job(facts["sha256"]); final=job/"final"; review=job/"review"; route_dir=out/f"{index:02d}_{job.name}"; route_dir.mkdir()
        release_report=route_dir/"release_qa.json"
        run([sys.executable,str(TOOLS/"validate_generic_release.py"),str(final),str(release_report)],route_dir/"release_qa.log")
        blend=next(final.glob("06_*.blend")); blender_report=route_dir/"blender_audit.json"
        run([str(BLENDER),"--background",str(blend),"--python",str(TOOLS/"audit_blender_delivery.py"),"--",str(blender_report)],route_dir/"blender_audit.log")
        one_plate=next(final.glob("05_*.3mf")); hierarchy_report=route_dir/"one_plate.json"
        run([sys.executable,str(TOOLS/"validate_bambu_four_object_plate.py"),str(one_plate),str(hierarchy_report)],route_dir/"one_plate.log")
        water=json.loads((review/"water_inserts.json").read_text(encoding="utf-8")); trail=json.loads((review/"trail_one_piece.json").read_text(encoding="utf-8")); release=json.loads(release_report.read_text()); blender=json.loads(blender_report.read_text()); hierarchy=json.loads(hierarchy_report.read_text())
        previews={name:(review/name).exists() and (review/name).stat().st_size>0 for name in ("blender_delivery.png","blender_delivery_top.png","blender_delivery_side.png")}
        files=sorted([{"name":p.name,"bytes":p.stat().st_size,"sha256":sha(p)} for p in final.iterdir() if p.suffix.lower() in {".3mf",".blend"}],key=lambda x:x["name"])
        blocking_checks={"gpx_two_steps_profile":facts["track_segments"]>=1 and facts["points"]>1,"input_hash_matches_job":json.loads((job/"job.json").read_text())["input_sha256"]==facts["sha256"],"five_plus_one":len(files)==6,"release_qa":release["status"]=="PASS","four_objects":hierarchy["status"]=="PASS","trail_one_piece":trail.get("components_after")==1,"final_three_views":all(previews.values()),"blender_materials":blender["status"]=="PASS"}
        warning_checks={"water_components_target_max_5":water["connectivity"]["components_after"]<=5}
        blockers=[key for key,value in blocking_checks.items() if not value]
        warnings=[key for key,value in warning_checks.items() if not value]
        status="BLOCKED" if blockers else ("PASS_WITH_WARNINGS" if warnings else "PASS")
        findings=([{"priority":"P0","scenario":"Q0-Q2","code":key} for key in blockers]
                  +[{"priority":"P1","scenario":"Q3_ASSEMBLABILITY","code":key,"message":"水系仍可交付，但组件多于 5 个会增加安装复杂度与断裂风险。"} for key in warnings]
                  +[{"priority":"P1","scenario":"Q3_ASSEMBLABILITY","code":"physical_print_assembly_not_automated","message":"本次自动回归没有产生该路线的真机打印与装配证据。"}])
        scenarios={
            "Q0_INPUT_TRACEABILITY":{"status":"PASS" if blocking_checks["gpx_two_steps_profile"] and blocking_checks["input_hash_matches_job"] else "FAIL","evidence":"E1"},
            "Q1_DELIVERY_INTEGRITY":{"status":"PASS" if blocking_checks["five_plus_one"] and blocking_checks["release_qa"] else "FAIL","evidence":"E1"},
            "Q2_PRINTABILITY":{"status":"PASS" if blocking_checks["four_objects"] and blocking_checks["trail_one_piece"] and blocking_checks["blender_materials"] else "FAIL","evidence":"E1 + separate user-confirmed Bambu open evidence"},
            "Q3_ASSEMBLABILITY":{"status":"NOT_TESTED","evidence":"No route-specific E5 evidence in this automated run"},
            "Q4_ENGINEERING_FIDELITY":{"status":"PASS" if blocking_checks["final_three_views"] else "FAIL","evidence":"E1/E2 partial; GIS fidelity not fully scored"},
            "Q5_CREATIVE_AESTHETICS":{"status":"NOT_TESTED","evidence":"Requires human review"},
            "Q6_USABILITY":{"status":"NOT_TESTED","evidence":"Requires Web user-flow test"},
        }
        routes.append({"route":gpx.stem,"gpx":str(gpx),"facts":facts,"job":job.name,"engineering":json.loads((job/"job.json").read_text()).get("engineering",{}),"checks":{**blocking_checks,**warning_checks},"blocking_checks":blocking_checks,"warning_checks":warning_checks,"quality_scenarios":scenarios,"findings":findings,"status":status,"water_components":water["connectivity"],"trail":trail,"one_plate":hierarchy,"blender":blender,"previews":previews,"files":files})
    overall="BLOCKED" if any(r["status"]=="BLOCKED" for r in routes) else ("PASS_WITH_WARNINGS" if any(r["status"]=="PASS_WITH_WARNINGS" for r in routes) else "PASS")
    payload={"schema_version":"2.0","quality_policy":"07_Knowledge/qa/quality_policy.json","generated_at":datetime.now().astimezone().isoformat(),"status":overall,"scope":"GPX→Web job→5x3MF+1xBlend automated regression","routes":routes,"manual_evidence":{"four_object_plate_opened_in_bambu_studio":"PASS (user confirmed for all 3 routes)","physical_print_assembly":"not covered by this automated run"}}
    (out/"report.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["# 三路线全面回归测试报告","",f"- 结果：**{overall}**",f"- 时间：{payload['generated_at']}","- 范围：GPX 输入、Web 任务溯源、5+1、三色地形、轨迹、水系、四件同盘、颜色、Z/打印盘、Blender 与三机位。","", "## 汇总","", "| 路线 | 点数/轨段 | 高程倍率 | 水系组件 | 四对象 | 最终三机位 | 结果 |","|---|---:|---:|---:|---|---|---|"]
    for r in routes: lines.append(f"| {r['route']} | {r['facts']['points']}/{r['facts']['track_segments']} | {r['engineering'].get('elevation_scale')} | {r['water_components']['components_after']} | {r['checks']['four_objects']} | {r['checks']['final_three_views']} | **{r['status']}** |")
    lines += ["","## 自动检查明细",""]
    for r in routes:
        lines += [f"### {r['route']}","",f"- 对应任务：`{r['job']}`"]
        lines += [f"- {'PASS' if value else 'BLOCKER'}：{key}" for key,value in r["blocking_checks"].items()]
        lines += [f"- {'PASS' if value else 'WARNING'}：{key}" for key,value in r["warning_checks"].items()]
        lines += ["- P1 / Q3：physical_print_assembly_not_automated","", "#### 场景成熟度", "", "| 场景 | 状态 | 证据 |", "|---|---|---|"]
        lines += [f"| {key} | {value['status']} | {value['evidence']} |" for key,value in r["quality_scenarios"].items()]
        lines += [""]
    lines += ["## 问题分级","","- **P0（阻断）**：阻止当前目标场景交付；基础打印或装配失败必须修复。","- **P1（重大风险）**：当前可能可用，但缺少真机证据或存在明显安装/强度风险；真机失败后升级 P0。","- **P2（一般问题）**：影响工程表达、创意或便利性，不阻断基本打印装配。","- **P3（优化建议）**：审美、效率和体验提升。","","## 事实、假设与边界","","- 事实：三条输入按 SHA-256 匹配各自最新完整 Web 任务，不按文件名猜测。","- 事实：用户已在 Bambu Studio 手动打开三条路线的四件同盘 3MF，并确认可用。","- 假设：这些 GPX 均代表当前标准的“两步路”导出输入。","- 边界：自动测试不能替代耗材、切片参数、打印强度和实际装配真机验收；未测试显示为 NOT_TESTED。","","## 结论","",f"当前数字回归结论：**{overall}**。Q0–Q2 用现有自动与 Bambu 打开证据评价；Q3 真机装配、Q5 创意和 Q6 便利性必须分别补证，不能被总体状态掩盖。",""]
    (out/"report.md").write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps({"status":overall,"output":str(out),"routes":[r["route"] for r in routes]},ensure_ascii=False))
    if overall=="BLOCKED": raise SystemExit(1)


if __name__=="__main__": main()
