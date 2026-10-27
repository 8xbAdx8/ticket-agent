"""启动器隔离、只读和凭据处理；不发送任何模型请求。"""
import contextlib
import io
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from scripts import launch_app


class LauncherTests(unittest.TestCase):
    def test_offline_rejects_inherited_live_and_mutation_settings(self):
        source={"DEEPSEEK_API_KEY":"test-launcher-key","DEEPSEEK_BUDGET_PATH":"formal.db",
                "DEEPSEEK_LIVE_TEST_PROFILE":"full_sandbox","AGENT_API_KEY":"other-key",
                "AGENT_PROVIDER":"deepseek","AGENT_MUTATIONS":'{"skip_lock":true}',"AGENT_USE_HTTP":"1"}
        before=dict(source)
        env=launch_app.build_environment("offline",Path("runtime"),source)
        self.assertEqual(source,before)
        self.assertEqual((env["AGENT_PROVIDER"],env["AGENT_ENGINE"],env["AGENT_LC_TOOLSET"]),("mock","legacy","all"))
        self.assertNotIn("DEEPSEEK_API_KEY",env)
        self.assertNotIn("AGENT_API_KEY",env)
        self.assertNotIn("DEEPSEEK_BUDGET_PATH",env)
        self.assertEqual(env["AGENT_MUTATIONS"],"{}")
        self.assertEqual(env["AGENT_USE_HTTP"],"0")

    def test_live_uses_own_ledger_and_read_only_without_changing_source(self):
        source={"DEEPSEEK_API_KEY":"test-launcher-key","DEEPSEEK_BUDGET_PATH":"formal.db",
                "DEEPSEEK_MAX_REQUESTS":"5","DEEPSEEK_LIVE_TEST_PROFILE":"full_sandbox",
                "DEEPSEEK_SANDBOX_DIR":"old-sandbox","AGENT_LC_TOOLSET":"all"}
        env=launch_app.build_environment("live",Path("runtime"),source)
        self.assertEqual(env["DEEPSEEK_API_KEY"],"test-launcher-key")
        self.assertEqual(env["DEEPSEEK_MAX_REQUESTS"],"0")
        self.assertEqual(Path(env["DEEPSEEK_BUDGET_PATH"]),Path("runtime/live/requests.db"))
        self.assertEqual(env["AGENT_LC_TOOLSET"],"read_only")
        self.assertEqual(env["DEEPSEEK_LIVE_TEST_PROFILE"],"read_only")
        self.assertNotIn("DEEPSEEK_SANDBOX_DIR",env)
        self.assertEqual(source["DEEPSEEK_BUDGET_PATH"],"formal.db")
        self.assertEqual(env["AGENT_MODEL"],"deepseek-flash")

    def test_manual_default_and_mode_data_isolation(self):
        offline=launch_app.build_environment("offline",Path("runtime"),{})
        live=launch_app.build_environment("live",Path("runtime"),{})
        self.assertNotEqual(offline["AGENT_DB_PATH"],live["AGENT_DB_PATH"])
        self.assertNotEqual(offline["AGENT_TRACE_DIR"],live["AGENT_TRACE_DIR"])
        self.assertEqual(live["DEEPSEEK_MAX_REQUESTS"],"0")
        self.assertEqual(launch_app.build_environment("live",Path("runtime"),{"DEEPSEEK_MAX_REQUESTS":"6"})["DEEPSEEK_MAX_REQUESTS"],"0")

    def test_fake_key_preflight_never_connects_or_creates_files(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(launch_app,"ROOT",Path(temp)),patch.dict("os.environ",{"DEEPSEEK_API_KEY":"test-launcher-secret"},clear=True),patch.object(launch_app,"missing_dependencies",return_value=[]),patch.object(socket.socket,"connect",side_effect=AssertionError("No network")),patch.object(launch_app,"serve",side_effect=AssertionError("No service")):
            text=io.StringIO()
            with contextlib.redirect_stdout(text):code=launch_app.main(["--mode","live","--check-only"])
            self.assertEqual(code,0)
            result=json.loads(text.getvalue())
            self.assertTrue(result["api_key_configured"])
            self.assertEqual(result["model_requests_sent"],0)
            self.assertNotIn("test-launcher-secret",text.getvalue())
            self.assertFalse(list(Path(temp).iterdir()))

    def test_missing_key_preflight_stops_without_prompt(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(launch_app,"ROOT",Path(temp)),patch.dict("os.environ",{},clear=True),patch.object(launch_app,"missing_dependencies",return_value=[]),patch.object(launch_app.getpass,"getpass",side_effect=AssertionError("No prompt")):
            text=io.StringIO()
            with contextlib.redirect_stdout(text):code=launch_app.main(["--mode","live","--check-only"])
            self.assertEqual(code,2)
            self.assertEqual(json.loads(text.getvalue())["status"],"missing_key")

    def test_existing_database_is_not_seeded_or_reset(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"tickets.db";path.write_bytes(b"keep-existing-bytes")
            with patch.object(launch_app.subprocess,"run",side_effect=AssertionError("Must not seed")):
                launch_app.prepare_database({"AGENT_DB_PATH":str(path)})
            self.assertEqual(path.read_bytes(),b"keep-existing-bytes")

    def test_budget_inspection_is_read_only(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"requests.db"
            self.assertEqual(launch_app.budget_count(path),0)
            self.assertFalse(path.exists())
            with contextlib.closing(sqlite3.connect(path)) as conn:
                conn.execute("CREATE TABLE requests(id INTEGER)")
                conn.execute("INSERT INTO requests VALUES (1)")
                conn.commit()
            before=path.read_bytes()
            self.assertEqual(launch_app.budget_count(path),1)
            self.assertEqual(path.read_bytes(),before)

    def test_busy_port_is_not_killed_or_reused(self):
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as server:
            if hasattr(socket,"SO_EXCLUSIVEADDRUSE"):server.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            server.bind(("127.0.0.1",0));server.listen(1)
            port=server.getsockname()[1]
            if port==65535:self.skipTest("no next port")
            self.assertNotEqual(launch_app.available_port(port),port)
            with self.assertRaises(ValueError):launch_app.available_port(port,exact=True)


if __name__=="__main__":unittest.main()
