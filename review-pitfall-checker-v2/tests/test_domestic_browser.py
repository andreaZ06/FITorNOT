import importlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class DomesticBrowserHelpersTest(unittest.TestCase):
    def test_build_browser_session_config_uses_explicit_profile_source_root(self):
        module = importlib.import_module("domestic_browser")

        with patch.dict(
            os.environ,
            {"FITORNOT_BROWSER_PROFILE_SOURCE_DIR": "C:/Users/test/AppData/Local/Google/Chrome/User Data"},
            clear=False,
        ):
            config = module.build_browser_session_config()

        self.assertEqual(
            Path(config["profile_source_root"]),
            Path("C:/Users/test/AppData/Local/Google/Chrome/User Data"),
        )
        self.assertTrue(config["sync_system_profile"])

    def test_build_browser_session_config_prefers_cdp_when_configured(self):
        module = importlib.import_module("domestic_browser")

        with patch.dict(os.environ, {"FITORNOT_BROWSER_CDP_URL": "http://127.0.0.1:9222"}, clear=False):
            config = module.build_browser_session_config()

        self.assertEqual(config["mode"], "cdp")
        self.assertEqual(config["cdp_url"], "http://127.0.0.1:9222")

    def test_detect_platform_block_reason_identifies_jd_login_wall(self):
        module = importlib.import_module("domestic_browser")

        reason = module.detect_platform_block_reason(
            "jd",
            "京东登录注册",
            "京东登录注册 获取验证码 账号密码登录",
        )

        self.assertIn("login", reason.lower())
        self.assertIn("jd", reason.lower())

    def test_detect_platform_block_reason_identifies_jd_welcome_login_variant(self):
        module = importlib.import_module("domestic_browser")

        reason = module.detect_platform_block_reason(
            "jd",
            "京东-欢迎登录",
            "个人用户登录 手机扫码安全登录 密码登录 短信登录 立即注册",
        )

        self.assertIn("login", reason.lower())
        self.assertIn("jd", reason.lower())

    def test_detect_platform_block_reason_identifies_xhs_login_prompt(self):
        module = importlib.import_module("domestic_browser")

        reason = module.detect_platform_block_reason(
            "xiaohongshu",
            "小红书 - 你的生活兴趣社区",
            "登录后推荐更懂你的笔记 小红书或微信扫码 手机号登录",
        )

        self.assertIn("login", reason.lower())
        self.assertIn("xiaohongshu", reason.lower())

    def test_detect_platform_block_reason_identifies_taobao_captcha_response(self):
        module = importlib.import_module("domestic_browser")

        reason = module.detect_platform_block_reason(
            "taobao",
            "淘宝搜索",
            "亲，请登录 所有宝贝 加载中...",
            [
                'mtopjsonp6({"ret":["FAIL_SYS_USER_VALIDATE","RGV587_ERROR::SM::哎哟喂,被挤爆啦"],'
                '"data":{"url":"https://login.taobao.com/member/login.jhtml"}})'
            ],
        )

        self.assertIn("taobao", reason.lower())
        self.assertTrue("captcha" in reason.lower() or "login" in reason.lower())

    def test_parse_taobao_search_response_extracts_candidates_from_jsonp(self):
        module = importlib.import_module("domestic_browser")
        response_text = """
        mtopjsonp6({
          "ret": ["SUCCESS::调用成功"],
          "data": {
            "result": [{
              "items": [{
                "title": "Anker Nano 10000mAh 充电宝",
                "price": "149.00",
                "nick": "Anker旗舰店",
                "itemId": "1234567890"
              }, {
                "title": "Anker 自带线 充电宝",
                "price": "199.00",
                "shopName": "Anker京东自营",
                "url": "https://detail.tmall.com/item.htm?id=998877"
              }]
            }]
          }
        })
        """

        candidates = module.parse_taobao_search_response(response_text, limit=5)

        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0]["title"], "Anker Nano 10000mAh 充电宝")
        self.assertEqual(candidates[0]["url"], "https://item.taobao.com/item.htm?id=1234567890")
        self.assertEqual(candidates[1]["platform"], "taobao")

    def test_cap_xhs_hits_limits_total_comments_to_twenty(self):
        module = importlib.import_module("domestic_browser")
        hits = [
            {
                "query": "Anker 10000 充电宝 避雷",
                "url": "https://www.xiaohongshu.com/explore/a",
                "notes": [{"text": "第一篇"}],
                "comments": [{"text": f"A{i}"} for i in range(15)],
                "platform": "xiaohongshu",
            },
            {
                "query": "Anker 10000 充电宝 缺点",
                "url": "https://www.xiaohongshu.com/explore/b",
                "notes": [{"text": "第二篇"}],
                "comments": [{"text": f"B{i}"} for i in range(15)],
                "platform": "xiaohongshu",
            },
        ]

        normalized = module.cap_xhs_hits(hits, total_comment_limit=20)

        self.assertEqual(sum(len(hit["comments"]) for hit in normalized), 20)
        self.assertEqual(normalized[0]["notes"][0]["text"], "第一篇")
        self.assertTrue(normalized[1]["comments"])

    def test_sync_browser_profile_copies_supported_auth_artifacts(self):
        module = importlib.import_module("domestic_browser")

        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source_root = Path(source_dir)
            target_root = Path(target_dir)
            (source_root / "Local State").write_text("{}", encoding="utf-8")
            (source_root / "lockfile").write_text("locked", encoding="utf-8")
            (source_root / "Default" / "Network").mkdir(parents=True)
            (source_root / "Default" / "Network" / "Cookies").write_text("cookie-db", encoding="utf-8")
            (source_root / "Default" / "Local Storage" / "leveldb").mkdir(parents=True)
            (source_root / "Default" / "Local Storage" / "leveldb" / "000001.ldb").write_text(
                "session",
                encoding="utf-8",
            )
            (source_root / "Default" / "Cache").mkdir(parents=True)
            (source_root / "Default" / "Cache" / "cache.bin").write_text("cache", encoding="utf-8")

            summary = module.sync_browser_profile(source_root, target_root)
            self.assertTrue(summary["copied"])
            self.assertTrue((target_root / "Local State").exists())
            self.assertTrue((target_root / "Default" / "Network" / "Cookies").exists())
            self.assertTrue((target_root / "Default" / "Local Storage" / "leveldb" / "000001.ldb").exists())
            self.assertFalse((target_root / "lockfile").exists())
            self.assertFalse((target_root / "Default" / "Cache").exists())

    def test_sync_browser_profile_returns_empty_summary_when_source_is_missing(self):
        module = importlib.import_module("domestic_browser")

        with tempfile.TemporaryDirectory() as target_dir:
            summary = module.sync_browser_profile(
                Path("C:/definitely-missing-fitornot-profile"),
                Path(target_dir),
            )

        self.assertFalse(summary["copied"])
        self.assertEqual(summary["copied_entries"], 0)

    def test_sync_browser_profile_falls_back_to_sqlite_backup_for_locked_cookie_db(self):
        module = importlib.import_module("domestic_browser")

        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source_root = Path(source_dir)
            target_root = Path(target_dir)
            cookie_db = source_root / "Default" / "Network" / "Cookies"
            cookie_db.parent.mkdir(parents=True)
            connection = sqlite3.connect(cookie_db)
            connection.execute("CREATE TABLE sample (value TEXT)")
            connection.execute("INSERT INTO sample(value) VALUES ('trusted-session')")
            connection.commit()
            connection.close()

            real_copy2 = module.shutil.copy2

            def flaky_copy2(source, destination, *args, **kwargs):
                if Path(source) == cookie_db:
                    raise PermissionError("file is locked")
                return real_copy2(source, destination, *args, **kwargs)

            with patch.object(module.shutil, "copy2", side_effect=flaky_copy2):
                summary = module.sync_browser_profile(source_root, target_root)

            self.assertTrue(summary["copied"])
            self.assertTrue((target_root / "Default" / "Network" / "Cookies").exists())
            copied_connection = sqlite3.connect(target_root / "Default" / "Network" / "Cookies")
            row = copied_connection.execute("SELECT value FROM sample").fetchone()
            copied_connection.close()
            self.assertEqual(row[0], "trusted-session")
            self.assertFalse(summary["errors"])


if __name__ == "__main__":
    unittest.main()
