import copy
import os
import shutil
import xml.etree.ElementTree as ET
import zipfile

DOCX_IN = r"C:\Users\Mayuresh Thakur\Downloads\chaosgate_backup.docx"
DOCX_FIXED = r"C:\Users\Mayuresh Thakur\Downloads\chaosgate_fixed.docx"
DOCX_TARGET = r"C:\Users\Mayuresh Thakur\Downloads\chaosgate.docx"

ns = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
}
ET.register_namespace("w", "http://schemas.openxmlformats.org/wordprocessingml/2006/main")
ET.register_namespace("r", "http://schemas.openxmlformats.org/officeDocument/2006/relationships")
ET.register_namespace("wp", "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing")
ET.register_namespace("a", "http://schemas.openxmlformats.org/drawingml/2006/main")
ET.register_namespace("pic", "http://schemas.openxmlformats.org/drawingml/2006/picture")

with zipfile.ZipFile(DOCX_IN, "r") as z_in:
    xml_content = z_in.read("word/document.xml")
    root = ET.fromstring(xml_content)

    paras = root.findall(".//w:p", ns)
    print(f"Loaded document.xml with {len(paras)} paragraphs")

    # 1. Fix Approval Sheet (Paragraph 19)
    p19 = paras[19]
    for r in p19.findall(".//w:r", ns):
        for t in r.findall(".//w:t", ns):
            if "Personal AI Research Assistant" in t.text:
                t.text = t.text.replace("Personal AI Research Assistant", "ChaosGate: A Unified DevSecOps Release Gate and Control Plane")
                print("Fixed Approval Sheet title in P19")

    # 2. Fix Certificate (Paragraph 54)
    p54 = paras[54]
    for r in p54.findall(".//w:r", ns):
        for t in r.findall(".//w:t", ns):
            if "Personal AI Research Assistant" in t.text:
                t.text = t.text.replace("Personal AI Research Assistant", "ChaosGate: A Unified DevSecOps Release Gate and Control Plane")
                print("Fixed Certificate title in P54")
            if "Second" in t.text:
                t.text = t.text.replace("Second", "Third")
                print("Fixed Certificate academic year in P54")

    # 3. Fix Survey figure captions (Paragraphs 223, 225, 229)
    for p_idx, new_title in [
        (223, "Fig 1: Survey Respondent Demographics & Roles (DevOps, Security & Resilience Survey)"),
        (225, "Fig 2: Primary CI/CD Tools Adopted by Development Teams (GitHub Actions 82.4%, GitLab 41.2%)"),
        (229, "Fig 3: Security Testing Frequency & Deployment Failure Benchmarks")
    ]:
        p = paras[p_idx]
        t_nodes = p.findall(".//w:t", ns)
        if t_nodes:
            t_nodes[0].text = new_title
            for extra in t_nodes[1:]:
                extra.text = ""
            print(f"Fixed caption in P{p_idx} -> {new_title}")

    # 4. Fix Section 4.1 placeholder (Paragraph 393)
    p393 = paras[393]
    t_nodes = p393.findall(".//w:t", ns)
    if t_nodes:
        t_nodes[0].text = "The user interface wireframes and structural blueprints for the ChaosGate web dashboard and GitHub PR integration are detailed below and cataloged in Appendix B."
        for extra in t_nodes[1:]:
            extra.text = ""
        print("Fixed Section 4.1 placeholder in P393")

    # 5. Fix Section 4.3 Flowchart (Paragraphs 414 to 475)
    # Paragraph 411: 4.3 Flowchart
    # Paragraph 412: Fig 5: Pipeline Execution Flowchart
    # Paragraph 413: The flowchart represents the decision logic of the ChaosGate pipeline:
    # Paragraphs 414-475: Scrambled numbers and reversed fragments.
    # We replace paragraph 414 with clear, clean structured decision logic and clear out 415-475.
    flowchart_explanation = [
        "The decision logic of the ChaosGate multi-stage verification pipeline executes as follows:",
        "[Step 1: PR Ingestion] - Developer opens or updates a Pull Request. GitHub emits a webhook event to ChaosGate.",
        "[Step 2: Stack Detection] - ChaosGate automatically scans dependency manifests (requirements.txt, package.json, Cargo.lock, go.mod) and identifies runtime language and framework.",
        "[Step 3: Pre-Flight Contract Validation] - Validates chaosgate.yml specification, required environment variables, and branch protection readiness.",
        "[Step 4: Unit & Build Verification] - Executes unit tests (pytest, npm test, cargo test, go test). IF FAILED -> Mark Gate FAILED, Block Merge, Post Diagnostics, EXIT.",
        "[Step 5: Supply Chain & Secret Scanning] - Scans git history for hardcoded credentials via regex rules and queries OSV.dev batch API for unpatched CVEs. IF CRITICAL SECRETS/CVES FOUND -> Mark Gate FAILED, Block Merge, Post Diagnostics, EXIT.",
        "[Step 6: Ephemeral Container Boot] - Builds application Docker image and boots container in isolated bridge network or ephemeral Kubernetes namespace.",
        "[Step 7: Synthetic Load Testing (k6)] - Injects virtual users simulating production concurrency. Compares p95 latency and HTTP error rates against thresholds. IF P95 EXCEEDED -> Mark Gate FAILED, Block Merge, EXIT.",
        "[Step 8: Chaos Injection & Resilience Probe] - Subjects running container to service restarts, traffic bursts, and corrupt HTTP requests to verify graceful degradation.",
        "[Step 9: Observability Telemetry Check] - Scrapes Prometheus metrics and evaluates SLA/SLO compliance.",
        "[Step 10: Composite Verdict & Merge Protection] - Aggregates scores across all 13 stages into an immutable composite verdict. IF ALL PASS -> Update GitHub Status Check to 'SUCCESS', Enable Merge Button. IF ANY FAIL -> Update Status Check to 'FAILED', GitHub Branch Protection physically disables the Merge Button.",
        "[Step 11: Post-Merge Incident & Automated Revert] - If regressions emerge post-merge, ChaosGate initiates an automated revert PR, verifies clean 3-way merge, and provides instant rollback path."
    ]

    p414 = paras[414]
    # Put first line in p414
    t_nodes = p414.findall(".//w:t", ns)
    if t_nodes:
        t_nodes[0].text = flowchart_explanation[0]
        for extra in t_nodes[1:]:
            extra.text = ""

    # Create new paragraphs for the remaining lines of flowchart right after p414
    parent = root.find(".//w:body", ns)
    # Find index of p414 in body
    p414_idx = list(parent).index(p414)
    for offset, line_text in enumerate(flowchart_explanation[1:], start=1):
        new_p = copy.deepcopy(p414)
        t_n = new_p.findall(".//w:t", ns)
        if t_n:
            t_n[0].text = line_text
            for extra in t_n[1:]:
                extra.text = ""
        parent.insert(p414_idx + offset, new_p)

    # Now remove all original broken paragraphs (which were originally 415 to 475)
    for p_to_remove in paras[415:476]:
        if p_to_remove in parent:
            parent.remove(p_to_remove)
    print("Cleaned up and restructured Section 4.3 Flowchart!")

    # 6. Update Section 4.2 Process Model (Paragraph 402-409)
    # Update stage descriptions to reflect the complete 13 stages
    # Let's locate P404-P409
    for p in root.findall(".//w:p", ns):
        text = "".join([t.text for t in p.findall(".//w:t", ns) if t.text])
        if "Stage 6 – Verdict Calculation & Enforcement:" in text:
            for t in p.findall(".//w:t", ns):
                if "Stage 6" in t.text:
                    t.text = t.text.replace(
                        "Stage 6 – Verdict Calculation & Enforcement:",
                        "Stage 13 – Composite Verdict Calculation & Branch Protection Enforcement:"
                    )
                    print("Updated Stage 6 to Stage 13 in Process Model")

    # 7. Update Chapter 7 Future Scope
    for p in root.findall(".//w:p", ns):
        text = "".join([t.text for t in p.findall(".//w:t", ns) if t.text])
        if "Advanced Chaos Engineering:" in text:
            for t in p.findall(".//w:t", ns):
                if "Advanced Chaos Engineering:" in text:
                    t.text = "Enterprise Chaos Mesh Integration: Expanding built-in chaos probes into live distributed Kubernetes clusters using Chaos Mesh / Litmus Chaos operators."
                    print("Updated Chaos Engineering in Future Scope")
        elif "Kubernetes Support:" in text:
            for t in p.findall(".//w:t", ns):
                if "Kubernetes Support:" in text:
                    t.text = "Multi-Tenant Cloud Control Plane: Transitioning from local single-tenant execution to hosted multi-tenant SaaS with GitHub OAuth2 App onboarding and SSO."
                    print("Updated Kubernetes Support in Future Scope")

    # 8. Update Chapter 8 Appendices descriptions
    for p in root.findall(".//w:p", ns):
        text = "".join([t.text for t in p.findall(".//w:t", ns) if t.text])
        if "Appendix F: Code Screenshots" in text:
            for t in p.findall(".//w:t", ns):
                if "Appendix F: Code Screenshots" in t.text:
                    t.text = "Appendix F: Code Implementation Artifacts (GitHub Actions Workflow chaosgate.yml, ChaosGate Specification contract, 13-Stage Pipeline Engine core/pipeline_service.py, Multi-Ecosystem Scanner core/supply_chain.py, Automated Revert core/recovery.py, and Kubernetes deployment manifests)"
                    print("Enriched Appendix F")
        elif "Appendix G: App Results Screenshots" in text:
            for t in p.findall(".//w:t", ns):
                if "Appendix G: App Results Screenshots" in t.text:
                    t.text = "Appendix G: Live Application Execution Screenshots (Control Plane Dashboard, Repository Catalog, Pipeline Run History, Green Gate Passed Verdict, Red Gate Blocked Verdict, Prometheus Telemetry, Policy Editor)"
                    print("Enriched Appendix G")

    new_xml = ET.tostring(root, encoding="utf-8")

# Now write back to DOCX_FIXED
with zipfile.ZipFile(DOCX_IN, "r") as z_in:
    with zipfile.ZipFile(DOCX_FIXED, "w", compression=zipfile.ZIP_DEFLATED) as z_out:
        for item in z_in.infolist():
            if item.filename == "word/document.xml":
                z_out.writestr(item, new_xml)
            else:
                z_out.writestr(item, z_in.read(item.filename))

print(f"Successfully wrote updated document to {DOCX_FIXED}")

try:
    shutil.copy2(DOCX_FIXED, DOCX_TARGET)
    print(f"Successfully copied to {DOCX_TARGET}")
except Exception as e:
    print(f"Could not overwrite {DOCX_TARGET} immediately (file currently open in Word): {e}")
    print(f"User can access the fully corrected file at: {DOCX_FIXED}")
