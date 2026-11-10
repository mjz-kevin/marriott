#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline tests for harness-invoke/scripts/preset_trigger.py (stdlib unittest, no network).

The templates below are the live runtime-input templates of the two registered
presets' pipelines (read 2026-11-10), so the rendered payload is exactly what a
real `harness_execute run` receives. Harness and the MCP config are replaced by
fakes; sensitive-data-guard's real scan.py runs on the written records.

Run: python .cursor/skills/cicd/harness-invoke/tests/run_tests.py
"""
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("preset_trigger", HERE.parent / "scripts" / "preset_trigger.py")
pt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pt)

STG = "https://interceptor-stg.csh.marriott.com.cn/v1/graph"

PROFILE = f"""\
mcp:
  github:
    repos:                             # comment
      ios:     {{ repo: cnexperience/ios-dragon-app,     base: develop }}
      android: {{ repo: cnexperience/android-dragon-app, base: dev }}
  harness:
    base_url: https://marriott.harness.io   # url keeps its colon
    org_id: cnexperience
    project_id: cnmobile
    pipelines:
      - {{ id: iOS_Dragon_App_Testflight_Dev, platform: ios, env: dev, usage: testflight, repo: ios-dragon-app }}
      - {{ id: Android_Adhoc_Build, platform: android, env: test, usage: adhoc, repo: android-dragon-app }}
      - {{ id: Some_Prod_Build, platform: ios, env: prod, repo: ios-dragon-app }}
    allowed_envs: [dev, test]
    build_backend_exceptions:
      - {{ pipeline: Android_Adhoc_Build, input: flavor, values: [Stg], backend: stg }}
      - {{ pipeline: iOS_Dragon_App_Testflight_Dev, input: API_BASE_URL, values: ["{STG}"], backend: stg }}
    default_presets:
      - {{ id: android-stg, pipeline: Android_Adhoc_Build, label: "Android STG 测试包", inputs: {{ flavor: Stg, variant: release, LOCALCMS_PREVIEWSECRET: "" }} }}
      - {{ id: ios-stg, pipeline: iOS_Dragon_App_Testflight_Dev, label: "iOS STG TestFlight 包", inputs: {{ API_BASE_URL: "{STG}", MARKETING_VERSION: "", LOCALCMS_PREVIEWSECRET: "" }} }}
      - {{ id: prod-env, pipeline: Some_Prod_Build, label: "x", inputs: {{}} }}
    poll:
      mode: server_wait
code:
  languages: [swift]
"""

IOS_TEMPLATE = """\
pipeline:
  identifier: iOS_Dragon_App_Testflight_Dev
  template:
    templateInputs:
      properties:
        ci:
          codebase:
            build: <+input>
      stages:
        - stage:
            identifier: Build
            type: CI
            spec:
              execution:
                steps:
                  - step:
                      identifier: Apply_Appdome
                      type: Run
                      spec:
                        envVariables:
                          APPDOME_IOS_FS_ID: <+input>.default(46b1c597-79b1-4efd-ab59-d58462c402d5)
            variables:
              - name: MARKETING_VERSION
                type: String
                value: <+input>
      variables:
        - name: API_BASE_URL
          type: String
          value: "<+input>.default(https://gatewaydsaptst1.marriott.com/v1/graph).selectOneFrom(https://interceptor-stg.csh.marriott.com.cn/v1/graph,https://interceptor-perf.marriott.com.cn/v1/graph,https://gatewaydsaptst1.marriott.com/v1/graph,https://gatewaydsapstg1.marriott.com/v1/graph)"
        - name: LOCALCMS_PREVIEWSECRET
          type: String
          value: <+input>
        - name: applyAppdome
          type: String
          value: "<+input>.default(false).selectOneFrom(true,false)"
        - name: uploadTo
          type: String
          value: "<+input>.default(Artifactory,TestFlight).selectManyFrom(Artifactory,TestFlight)"
"""

ANDROID_TEMPLATE = """\
pipeline:
  identifier: Android_Adhoc_Build
  properties:
    ci:
      codebase:
        build: <+input>
  stages:
    - stage:
        identifier: Build_Adhoc_APK
        type: CI
        spec:
          execution:
            steps:
              - step:
                  identifier: Gather_Build_Parameters
                  type: Run
                  spec:
                    envVariables:
                      flavor: "<+input>.default(Tst).allowedValues(Tst,Tst2,Uat2,Stg,Perf,Prod)"
                      variant: "<+input>.default(debug).allowedValues(debug,release)"
                      appdomeFusionSet: "<+input>.default(LLE).allowedValues(LLE,Prod)"
  variables:
    - name: appdomeProdFusionSetId
      type: String
      value: <+input>.default(6dc3f7b8-baa5-4705-87ba-a6b34af6f71f)
    - name: apiClientId
      type: String
      value: "<+input>.default(marriott_android).selectOneFrom(cn_marriott_android,marriott_android)"
    - name: LOCALCMS_PREVIEWSECRET
      type: String
      value: <+input>
"""

CI_PIPELINE = "pipeline:\n  stages:\n    - stage:\n        type: Custom\n        environmentRef: ios_appdome_uat\n    - stage:\n        type: CI\n"
CD_PIPELINE = CI_PIPELINE + "    - stage:\n        type: Deployment\n"


def profile(text=PROFILE):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "app-test.yaml"
        path.write_text(text, encoding="utf-8")
        return pt.load_profile(path)


def stop_code(fn, *args):
    try:
        fn(*args)
    except pt.Stop as stop:
        return stop.code, stop.reason
    return None, None


class FlowTest(unittest.TestCase):
    def test_nested_flow_with_urls(self):
        value = pt.parse_flow(f'{{ id: a, inputs: {{ U: "{STG}", E: "" }}, values: [Stg, "x,y"], n: null }}')
        self.assertEqual(value, {"id": "a", "inputs": {"U": STG, "E": ""}, "values": ["Stg", "x,y"], "n": None})

    def test_strip_comment_keeps_quoted_hash(self):
        self.assertEqual(pt.strip_comment('a: "x # y"   # note'), 'a: "x # y"')

    def test_load_profile(self):
        p = profile()
        self.assertEqual(p["scope"]["base_url"], "https://marriott.harness.io")
        self.assertEqual(p["allowed_envs"], ["dev", "test"])
        self.assertEqual(len(p["pipelines"]), 3)
        self.assertEqual(p["presets"][1]["inputs"]["API_BASE_URL"], STG)
        self.assertEqual(p["exceptions"][1]["values"], [STG])
        self.assertEqual(p["repos"]["android"]["base"], "dev")


class TemplateTest(unittest.TestCase):
    def test_slots(self):
        _, slots = pt.parse_template(IOS_TEMPLATE)
        self.assertEqual(set(slots), {"branch", "APPDOME_IOS_FS_ID", "MARKETING_VERSION", "API_BASE_URL",
                                      "LOCALCMS_PREVIEWSECRET", "applyAppdome", "uploadTo"})
        self.assertEqual(slots["branch"]["kind"], "codebase")
        self.assertIsNone(slots["MARKETING_VERSION"]["default"])
        self.assertEqual(slots["uploadTo"]["default"], "Artifactory,TestFlight")
        self.assertTrue(slots["uploadTo"]["multi"])
        self.assertIn(STG, slots["API_BASE_URL"]["allowed"])

    def test_duplicate_name_is_drift(self):
        code, _ = stop_code(pt.parse_template, IOS_TEMPLATE + "        - name: uploadTo\n          value: <+input>\n")
        self.assertEqual(code, pt.EXIT_DRIFT)


class EvaluateTest(unittest.TestCase):
    def test_ios_preset_payload(self):
        r = pt.evaluate(profile(), "ios-stg", "develop", IOS_TEMPLATE, CI_PIPELINE)
        self.assertEqual(r["scope"]["verdict"], "in_scope")
        self.assertIn("API_BASE_URL", r["scope"]["backend_exception"])
        self.assertEqual(r["branch_check"], "baseline")
        self.assertEqual(r["defaults"], {"APPDOME_IOS_FS_ID": "46b1c597-79b1-4efd-ab59-d58462c402d5",
                                         "applyAppdome": "false", "uploadTo": "Artifactory,TestFlight"})
        payload = r["run_args"]["inputs"]
        self.assertNotIn("<+input>", payload)
        self.assertIn('            build:\n              type: branch\n              spec:\n                branch: "develop"',
                      payload)
        self.assertIn(f'          value: "{STG}"', payload)
        self.assertIn('                value: ""', payload)
        self.assertEqual(r["run_args"]["wait"], False)
        self.assertEqual(r["run_args"]["resource_id"], "iOS_Dragon_App_Testflight_Dev")

    def test_android_preset_and_branch_checks(self):
        p = profile()
        r = pt.evaluate(p, "android-stg", "feature/x", ANDROID_TEMPLATE, "pipeline:\n  stages:\n    - stage:\n        type: CI\n")
        self.assertEqual(r["branch_check"], "needs_check")
        self.assertEqual(r["defaults"]["appdomeFusionSet"], "LLE")
        self.assertIn('flavor: "Stg"', r["run_args"]["inputs"])
        self.assertIsNone(pt.evaluate(p, "android-stg", None, ANDROID_TEMPLATE, "")["run_args"])

    def test_drift(self):
        p = profile()
        missing = IOS_TEMPLATE.replace("        - name: LOCALCMS_PREVIEWSECRET\n          type: String\n          value: <+input>\n", "")
        self.assertEqual(stop_code(pt.evaluate, p, "ios-stg", "develop", missing, CI_PIPELINE)[0], pt.EXIT_DRIFT)
        not_permitted = IOS_TEMPLATE.replace("https://interceptor-stg.csh.marriott.com.cn/v1/graph,", "")
        self.assertEqual(stop_code(pt.evaluate, p, "ios-stg", "develop", not_permitted, CI_PIPELINE)[0], pt.EXIT_DRIFT)
        required = IOS_TEMPLATE + "        - name: NEW_REQUIRED\n          type: String\n          value: <+input>\n"
        code, reason = stop_code(pt.evaluate, p, "ios-stg", "develop", required, CI_PIPELINE)
        self.assertEqual(code, pt.EXIT_DRIFT)
        self.assertIn("NEW_REQUIRED", reason)
        unknown = IOS_TEMPLATE.replace(".default(false).", ".default(false).weird(1).")
        self.assertEqual(stop_code(pt.evaluate, p, "ios-stg", "develop", unknown, CI_PIPELINE)[0], pt.EXIT_DRIFT)
        self.assertEqual(stop_code(pt.evaluate, p, "nope", "develop", IOS_TEMPLATE, CI_PIPELINE)[0], pt.EXIT_DRIFT)

    def test_credential_must_be_empty(self):
        text = PROFILE.replace('variant: release, LOCALCMS_PREVIEWSECRET: ""', 'variant: release, LOCALCMS_PREVIEWSECRET: "abc"')
        self.assertEqual(stop_code(pt.evaluate, profile(text), "android-stg", "dev", ANDROID_TEMPLATE, "")[0], pt.EXIT_DRIFT)

    def test_out_of_scope(self):
        unregistered = PROFILE.replace(f'API_BASE_URL: "{STG}", MARKETING', 'API_BASE_URL: "https://gatewaydsapstg1.marriott.com/v1/graph", MARKETING')
        code, reason = stop_code(pt.evaluate, profile(unregistered), "ios-stg", "develop", IOS_TEMPLATE, CI_PIPELINE)
        self.assertEqual(code, pt.EXIT_OUT_OF_SCOPE)
        self.assertIn("gatewaydsapstg1", reason)
        # a Harness default naming prod is out of scope too, even when the preset is fine
        prod_default = ANDROID_TEMPLATE.replace(".default(LLE)", ".default(Prod)")
        code, reason = stop_code(pt.evaluate, profile(), "android-stg", "dev", prod_default, "")
        self.assertEqual(code, pt.EXIT_OUT_OF_SCOPE)
        self.assertIn("Harness default", reason)
        # the exception covers a pure-CI build only
        self.assertEqual(stop_code(pt.evaluate, profile(), "ios-stg", "develop", IOS_TEMPLATE, CD_PIPELINE)[0],
                         pt.EXIT_OUT_OF_SCOPE)
        # the pipeline's own env tag must be allowlisted
        self.assertEqual(stop_code(pt.evaluate, profile(), "prod-env", "develop", "pipeline:\n", "")[0],
                         pt.EXIT_OUT_OF_SCOPE)
        # an exception on another pipeline never applies
        swapped = PROFILE.replace("{ pipeline: Android_Adhoc_Build, input: flavor", "{ pipeline: iOS_Dragon_App_Testflight_Dev, input: flavor")
        self.assertEqual(stop_code(pt.evaluate, profile(swapped), "android-stg", "dev", ANDROID_TEMPLATE, "")[0],
                         pt.EXIT_OUT_OF_SCOPE)


class RecordAdoptTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmp.name) / "app-ios-stg-develop"
        self.p = profile()
        pt.load_context = lambda name: (self.p, {"base_url": "https://h", "account_id": "acc", "api_key": "k"})
        pt.prepare = lambda prof, conn, preset, branch: (
            pt.evaluate(prof, preset, branch, IOS_TEMPLATE, CI_PIPELINE), IOS_TEMPLATE)
        pt.platform_paths.load_harness_connection = lambda: {"base_url": "https://h", "account_id": "acc", "api_key": "k"}
        pt.SCAN_EXTRA_ARGS = ["--no-log"]

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = pt.main(list(argv))
        return code, buf.getvalue()

    def record(self, answer="Use default: iOS STG TestFlight 包 · branch develop"):
        return self.cli("record", "--preset", "ios-stg", "--branch", "develop", "--run-dir", str(self.run_dir),
                        "--trigger", "3", "--answer", answer)

    def result(self):
        return json.loads((self.run_dir / "tmp" / "t3_result.json").read_text(encoding="utf-8"))

    def test_record_then_adopt(self):
        code, out = self.record()
        self.assertEqual(code, pt.EXIT_OK, out)
        res = self.result()
        self.assertEqual(res["trigger_outcome"], pt.OUTCOME_PENDING)
        self.assertNotIn("<+input>", res["run_args"]["inputs"])
        self.assertTrue((self.run_dir / res["params_log"]).is_file())
        session = (self.run_dir / res["session_record"]).read_text(encoding="utf-8")
        self.assertIn("> Use default: iOS STG TestFlight 包 · branch develop", session)
        self.assertEqual(len(list((self.run_dir / "inputs").glob("*_t3_runtime-input-template.yaml"))), 1)

        code, out = self.record()
        self.assertEqual(code, pt.EXIT_ALREADY_RECORDED, out)

        code, out = self.cli("adopt", "--run-dir", str(self.run_dir), "--trigger", "3",
                             "--execution-id", "abc", "--build-number", "3746")
        self.assertEqual(code, pt.EXIT_OK, out)
        res = self.result()
        self.assertEqual((res["execution_id"], res["build_number"], res["trigger_outcome"]), ("abc", 3746, "sent"))
        self.assertIn("/deployments/abc/pipeline", res["url"])
        code, _ = self.cli("adopt", "--run-dir", str(self.run_dir), "--trigger", "3", "--execution-id", "other")
        self.assertEqual(code, pt.EXIT_ERROR)
        code, _ = self.cli("adopt", "--run-dir", str(self.run_dir), "--trigger", "3", "--cancelled")
        self.assertEqual(code, pt.EXIT_ERROR)

    def test_cancelled_can_be_recorded_again(self):
        self.assertEqual(self.record()[0], pt.EXIT_OK)
        self.assertEqual(self.cli("adopt", "--run-dir", str(self.run_dir), "--trigger", "3", "--cancelled")[0], pt.EXIT_OK)
        self.assertEqual(self.result()["trigger_outcome"], pt.OUTCOME_NOT_SENT)
        self.assertEqual(self.record("Use default again")[0], pt.EXIT_OK)
        self.assertEqual(self.result()["trigger_outcome"], pt.OUTCOME_PENDING)

    def test_failed_is_unknown_and_blocks_rerecord(self):
        self.record()
        self.cli("adopt", "--run-dir", str(self.run_dir), "--trigger", "3", "--failed", "timeout")
        self.assertEqual(self.result()["trigger_outcome"], pt.OUTCOME_UNKNOWN)
        self.assertEqual(self.record()[0], pt.EXIT_ALREADY_RECORDED)

    def test_guard_blocks_secret_answer(self):
        code, _ = self.record("use default, token ghp_" + "a" * 36)
        self.assertEqual(code, pt.EXIT_ERROR)
        self.assertFalse((self.run_dir / "tmp" / "t3_result.json").exists())
        self.assertFalse((self.run_dir / "params").exists())


if __name__ == "__main__":
    unittest.main(verbosity=1)
