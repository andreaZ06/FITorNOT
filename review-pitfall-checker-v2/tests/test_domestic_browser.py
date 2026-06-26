import asyncio
import importlib
import gzip
import json
import os
import sqlite3
import tempfile
import unittest
from base64 import b64encode
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(PROJECT_ROOT))


class DomesticBrowserHelpersTest(unittest.TestCase):
    def test_start_browser_script_honors_fitornot_browser_profile_dir_env_var(self):
        script_path = Path(__file__).resolve().parents[1] / "start_fitornot_browser.ps1"
        script_text = script_path.read_text(encoding="utf-8")

        self.assertIn("FITORNOT_BROWSER_PROFILE_DIR", script_text)

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

    def test_build_browser_session_config_reads_cdp_url_from_profile_marker(self):
        module = importlib.import_module("domestic_browser")

        with tempfile.TemporaryDirectory() as profile_dir:
            marker = Path(profile_dir) / "cdp-url.txt"
            marker.write_text("http://127.0.0.1:9333", encoding="utf-8")

            with patch.dict(os.environ, {"FITORNOT_BROWSER_CDP_URL": ""}, clear=False):
                config = module.build_browser_session_config(profile_dir)

        self.assertEqual(config["mode"], "cdp")
        self.assertEqual(config["cdp_url"], "http://127.0.0.1:9333")

    def test_build_browser_session_config_strips_utf8_bom_from_cdp_marker(self):
        module = importlib.import_module("domestic_browser")

        with tempfile.TemporaryDirectory() as profile_dir:
            marker = Path(profile_dir) / "cdp-url.txt"
            marker.write_text("\ufeffhttp://127.0.0.1:9222", encoding="utf-8")

            with patch.dict(os.environ, {"FITORNOT_BROWSER_CDP_URL": ""}, clear=False):
                config = module.build_browser_session_config(profile_dir)

        self.assertEqual(config["cdp_url"], "http://127.0.0.1:9222")

    def test_build_browser_session_config_prefers_cdp_when_configured(self):
        module = importlib.import_module("domestic_browser")

        with patch.dict(os.environ, {"FITORNOT_BROWSER_CDP_URL": "http://127.0.0.1:9222"}, clear=False):
            config = module.build_browser_session_config()

        self.assertEqual(config["mode"], "cdp")
        self.assertEqual(config["cdp_url"], "http://127.0.0.1:9222")

    def test_resolve_cdp_connection_target_rewrites_remote_websocket_url_for_proxy_host(self):
        module = importlib.import_module("domestic_browser")

        async def fake_fetch(_url: str, headers: dict[str, str]) -> dict[str, str]:
            self.assertEqual(headers, {"Host": "localhost"})
            return {"webSocketDebuggerUrl": "ws://localhost/devtools/browser/test-browser-id"}

        endpoint_url, headers = asyncio.run(
            module.resolve_cdp_connection_target(
                "http://reseau.proxy.rlwy.net:41616",
                version_fetcher=fake_fetch,
            )
        )

        self.assertEqual(endpoint_url, "ws://reseau.proxy.rlwy.net:41616/devtools/browser/test-browser-id")
        self.assertEqual(headers, {"Host": "localhost"})

    def test_build_browser_session_config_defaults_to_bundled_chromium_without_browser_channel(self):
        module = importlib.import_module("domestic_browser")

        with patch.dict(
            os.environ,
            {
                "FITORNOT_BROWSER_CDP_URL": "",
                "FITORNOT_BROWSER_CHANNEL": "",
                "LOCALAPPDATA": "",
            },
            clear=False,
        ):
            config = module.build_browser_session_config()

        self.assertEqual(config["mode"], "persistent")
        self.assertIsNone(config["channel"])

    def test_build_browser_session_config_reads_seed_cookies_from_json_env(self):
        module = importlib.import_module("domestic_browser")
        cookie_payload = json.dumps(
            [
                {
                    "name": "pt_key",
                    "value": "jd-session",
                    "domain": ".jd.com",
                    "path": "/",
                }
            ]
        )

        with patch.dict(
            os.environ,
            {
                "FITORNOT_BROWSER_COOKIES_JSON": cookie_payload,
                "FITORNOT_BROWSER_CDP_URL": "",
            },
            clear=False,
        ):
            config = module.build_browser_session_config()

        self.assertEqual(len(config["seed_cookies"]), 1)
        self.assertEqual(config["seed_cookies"][0]["name"], "pt_key")

    def test_build_browser_session_config_reads_seed_cookies_from_default_profile_file(self):
        module = importlib.import_module("domestic_browser")

        with tempfile.TemporaryDirectory() as profile_dir:
            seed_file = Path(profile_dir) / "seed-cookies.json"
            seed_file.write_text(
                json.dumps(
                    {
                        "cookies": [
                            {
                                "name": "web_session",
                                "value": "xhs-session",
                                "domain": ".xiaohongshu.com",
                                "path": "/",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "FITORNOT_BROWSER_COOKIES_JSON": "",
                    "FITORNOT_BROWSER_COOKIES_FILE": "",
                    "FITORNOT_BROWSER_CDP_URL": "",
                },
                clear=False,
            ):
                config = module.build_browser_session_config(profile_dir)

        self.assertEqual(len(config["seed_cookies"]), 1)
        self.assertEqual(config["seed_cookies"][0]["domain"], ".xiaohongshu.com")

    def test_build_browser_session_config_reads_seed_storage_state_from_env(self):
        module = importlib.import_module("domestic_browser")
        storage_state_payload = {
            "cookies": [
                {
                    "name": "xhs.sid",
                    "value": "trusted",
                    "domain": ".xiaohongshu.com",
                    "path": "/",
                }
            ],
            "origins": [
                {
                    "origin": "https://www.xiaohongshu.com",
                    "localStorage": [{"name": "web_session", "value": "trusted-session"}],
                }
            ],
        }
        encoded_payload = "base64:" + b64encode(
            gzip.compress(json.dumps(storage_state_payload).encode("utf-8"))
        ).decode("ascii")

        with patch.dict(
            os.environ,
            {
                "FITORNOT_BROWSER_STORAGE_STATE": encoded_payload,
                "FITORNOT_BROWSER_STORAGE_STATE_FILE": "",
                "FITORNOT_BROWSER_CDP_URL": "",
            },
            clear=False,
        ):
            config = module.build_browser_session_config()

        self.assertEqual(config["seed_storage_state"]["cookies"][0]["name"], "xhs.sid")
        self.assertEqual(
            config["seed_storage_state"]["origins"][0]["localStorage"][0]["name"],
            "web_session",
        )

    def test_build_browser_session_config_reads_seed_storage_state_from_default_profile_file(self):
        module = importlib.import_module("domestic_browser")
        storage_state_payload = {
            "cookies": [
                {
                    "name": "pt_key",
                    "value": "jd-trusted",
                    "domain": ".jd.com",
                    "path": "/",
                }
            ],
            "origins": [],
        }

        with tempfile.TemporaryDirectory() as profile_dir:
            storage_state_file = Path(profile_dir) / "seed-storage-state.json"
            storage_state_file.write_text(json.dumps(storage_state_payload), encoding="utf-8")

            with patch.dict(
                os.environ,
                {
                    "FITORNOT_BROWSER_STORAGE_STATE": "",
                    "FITORNOT_BROWSER_STORAGE_STATE_FILE": "",
                    "FITORNOT_BROWSER_CDP_URL": "",
                },
                clear=False,
            ):
                config = module.build_browser_session_config(profile_dir)

        self.assertEqual(config["seed_storage_state"]["cookies"][0]["name"], "pt_key")

    def test_compact_seed_storage_state_filters_unrelated_domains(self):
        module = importlib.import_module("domestic_browser")
        compacted = module.compact_seed_storage_state(
            {
                "cookies": [
                    {
                        "name": "pt_key",
                        "value": "jd-trusted",
                        "domain": ".jd.com",
                        "path": "/",
                    },
                    {
                        "name": "gh",
                        "value": "ignore-me",
                        "domain": ".github.com",
                        "path": "/",
                    },
                ],
                "origins": [
                    {
                        "origin": "https://www.xiaohongshu.com",
                        "localStorage": [{"name": "web_session", "value": "trusted"}],
                    },
                    {
                        "origin": "https://example.com",
                        "localStorage": [{"name": "noise", "value": "drop"}],
                    },
                ],
            }
        )

        self.assertEqual(len(compacted["cookies"]), 1)
        self.assertEqual(compacted["cookies"][0]["domain"], ".jd.com")
        self.assertEqual(len(compacted["origins"]), 1)
        self.assertEqual(compacted["origins"][0]["origin"], "https://www.xiaohongshu.com")

    def test_compact_seed_storage_state_keeps_known_auth_keys_and_drops_cache_blobs(self):
        module = importlib.import_module("domestic_browser")

        compacted = module.compact_seed_storage_state(
            {
                "cookies": [],
                "origins": [
                    {
                        "origin": "https://www.xiaohongshu.com",
                        "localStorage": [
                            {"name": "redmoji", "value": "x" * 4000},
                            {"name": "b1", "value": "trusted-device"},
                            {"name": "RWP_LOGIN_TOKEN", "value": "trusted-login"},
                            {"name": "xhs-pc-search-history-5a07289111be101a125a20cb", "value": "history"},
                        ],
                    },
                    {
                        "origin": "https://www.jd.com",
                        "localStorage": [
                            {"name": "PC_HOME_MAIL_Resp", "value": "mail-cache"},
                            {"name": "__we_m_token__", "value": "trusted-jd-token"},
                            {"name": "__we_m_cf__", "value": "trusted-jd-fingerprint"},
                        ],
                    },
                    {
                        "origin": "https://www.taobao.com",
                        "localStorage": [
                            {"name": "PC_INDEX_dataCache_33667440", "value": "huge-cache"},
                            {"name": "APLUS_CORE_1.0.20_20260108171550_39484283", "value": "analytics"},
                            {"name": "tfstk__", "value": "trusted-taobao-token"},
                            {"name": "baxia_entry_config", "value": "trusted-baxia-config"},
                        ],
                    },
                ],
            }
        )

        compacted_by_origin = {
            origin["origin"]: {item["name"] for item in origin.get("localStorage", [])}
            for origin in compacted["origins"]
        }

        self.assertEqual(
            compacted_by_origin["https://www.xiaohongshu.com"],
            {"b1", "RWP_LOGIN_TOKEN"},
        )
        self.assertEqual(
            compacted_by_origin["https://www.jd.com"],
            {"__we_m_token__", "__we_m_cf__"},
        )
        self.assertEqual(
            compacted_by_origin["https://www.taobao.com"],
            {"tfstk__", "baxia_entry_config"},
        )

    def test_encode_seed_storage_state_payload_round_trips_through_loader(self):
        module = importlib.import_module("domestic_browser")
        storage_state_payload = {
            "cookies": [
                {
                    "name": "mtop",
                    "value": "taobao-trusted",
                    "domain": ".taobao.com",
                    "path": "/",
                }
            ],
            "origins": [],
        }
        encoded_payload = module.encode_seed_storage_state_payload(storage_state_payload)

        with patch.dict(
            os.environ,
            {
                "FITORNOT_BROWSER_STORAGE_STATE": encoded_payload,
                "FITORNOT_BROWSER_STORAGE_STATE_FILE": "",
            },
            clear=False,
        ):
            loaded_payload = module.load_browser_seed_storage_state()

        self.assertTrue(encoded_payload.startswith("base64:"))
        self.assertEqual(loaded_payload["cookies"][0]["name"], "mtop")

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

    def test_detect_platform_block_reason_identifies_jd_frequency_limit(self):
        module = importlib.import_module("domestic_browser")

        reason = module.detect_platform_block_reason(
            "jd",
            "Anker 1000 - 商品搜索 - 京东",
            "抱歉由于访问频繁导致无法搜索，请稍后再试！ 若长时间无法搜索可点此反馈",
        )

        self.assertIn("jd", reason.lower())
        self.assertTrue("frequent" in reason.lower() or "search" in reason.lower())

    def test_detect_platform_block_reason_identifies_jd_verification_wall(self):
        module = importlib.import_module("domestic_browser")

        reason = module.detect_platform_block_reason(
            "jd",
            "京东验证",
            "验证一下，购物无忧 快速验证 遇到问题点我反馈",
        )

        self.assertIn("jd", reason.lower())
        self.assertTrue("verification" in reason.lower() or "trusted browser session" in reason.lower())

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

    def test_parse_jd_search_cards_extracts_candidates_from_current_card_shape(self):
        module = importlib.import_module("domestic_browser")

        candidates = module.parse_jd_search_cards(
            [
                {
                    "sku": "100241293249",
                    "title": "ANKER zolo安克【新3C认证上飞机】充电宝自带双c线10000毫安mAh大容量35W快充移动电源安卓苹果手机白",
                    "price": "¥ 116 . 2",
                    "shop_name": "Anker京东自营旗舰店",
                    "text": "ANKER zolo安克【新3C认证上飞机】充电宝自带双c线10000毫安mAh大容量35W快充移动电源安卓苹果手机白 3C认证手机移动电源折扣榜第3名 轻薄便携 |双C线设计 |35W快充 |大容量续航 ¥ 116 . 2 已售5万+ Anker京东自营旗舰店",
                },
                {
                    "sku": "10222945730904",
                    "title": "ANKER安克Air磁吸无线快充移动电源2026新国标3C认证可上飞机小巧便携苹果适用 10000mAh",
                    "price": "¥ 1275",
                    "shop_name": "防晒运动好物优选店",
                    "text": "ANKER安克Air磁吸无线快充移动电源2026新国标3C认证可上飞机小巧便携苹果适用 10000mAh ¥ 1275 100%好评 防晒运动好物优选店",
                },
            ],
            limit=5,
        )

        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0]["platform"], "jd")
        self.assertEqual(candidates[0]["url"], "https://item.jd.com/100241293249.html")
        self.assertEqual(candidates[0]["price"], "116.2")
        self.assertIn("Anker京东自营旗舰店", candidates[0]["shop_name"])

    def test_normalize_xhs_search_candidates_prefers_search_result_title_over_blank_explore_link(self):
        module = importlib.import_module("domestic_browser")

        normalized = module.normalize_xhs_search_candidates(
            [
                {
                    "url": "https://www.xiaohongshu.com/explore/6845123a000000000c039899",
                    "title": "",
                    "text": "",
                    "class_name": "",
                },
                {
                    "url": "https://www.xiaohongshu.com/search_result/6845123a000000000c039899?xsec_token=abc",
                    "title": "安克双线充电宝首充使用感受记录",
                    "text": "安克双线充电宝首充使用感受记录 毛绒绒 2025-06-08 58",
                    "class_name": "title",
                },
            ],
            limit=5,
        )

        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0]["title"], "安克双线充电宝首充使用感受记录")
        self.assertIn("/search_result/6845123a000000000c039899", normalized[0]["url"])

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

    def test_sync_browser_profile_falls_back_to_esentutl_when_sqlite_backup_fails(self):
        module = importlib.import_module("domestic_browser")

        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source_root = Path(source_dir)
            target_root = Path(target_dir)
            cookie_db = source_root / "Default" / "Network" / "Cookies"
            cookie_db.parent.mkdir(parents=True)
            cookie_db.write_text("locked-cookie-db", encoding="utf-8")

            real_copy2 = module.shutil.copy2

            def flaky_copy2(source, destination, *args, **kwargs):
                if Path(source) == cookie_db:
                    raise PermissionError("file is locked")
                return real_copy2(source, destination, *args, **kwargs)

            copied_targets = []

            def fake_esentutl(source, destination):
                copied_targets.append((Path(source), Path(destination)))
                Path(destination).write_text("copied-with-esentutl", encoding="utf-8")
                return True

            with (
                patch.object(module.shutil, "copy2", side_effect=flaky_copy2),
                patch.object(module, "_copy_sqlite_database", return_value=False),
                patch.object(module, "_copy_file_with_esentutl", side_effect=fake_esentutl),
            ):
                summary = module.sync_browser_profile(source_root, target_root)

            self.assertTrue(summary["copied"])
            self.assertEqual(copied_targets[0][0], cookie_db)
            self.assertTrue((target_root / "Default" / "Network" / "Cookies").exists())
            self.assertEqual(
                (target_root / "Default" / "Network" / "Cookies").read_text(encoding="utf-8"),
                "copied-with-esentutl",
            )
            self.assertFalse(summary["errors"])

    def test_build_persistent_launch_options_include_container_safe_flags(self):
        module = importlib.import_module("domestic_browser")

        options = module.build_persistent_launch_options(
            profile_dir=Path("C:/fitornot/profile"),
            headless=True,
            session_config={
                "user_agent": "fitornot-agent",
                "extra_http_headers": {"Accept-Language": "zh-CN"},
                "channel": None,
            },
        )

        self.assertIn("--no-sandbox", options["args"])
        self.assertIn("--disable-dev-shm-usage", options["args"])
        self.assertIn("--disable-gpu", options["args"])


class DomesticBrowserAdapterAsyncTest(unittest.IsolatedAsyncioTestCase):
    async def test_lazy_scroll_prefers_dom_scroll_without_mouse_wheel(self):
        module = importlib.import_module("domestic_browser")
        adapter = module.PlaywrightDomesticBrowserAdapter(headless=True)
        evaluate_calls: list[str] = []
        wheel_calls: list[tuple[int, int]] = []

        async def fake_evaluate(script):
            evaluate_calls.append(script)

        async def fake_wheel(delta_x, delta_y):
            wheel_calls.append((delta_x, delta_y))

        page = SimpleNamespace(
            evaluate=fake_evaluate,
            mouse=SimpleNamespace(wheel=fake_wheel),
        )

        await adapter._lazy_scroll(page, rounds=2)

        self.assertEqual(len(evaluate_calls), 2)
        self.assertEqual(wheel_calls, [])

    async def test_apply_seed_cookies_adds_cookies_to_context(self):
        module = importlib.import_module("domestic_browser")
        recorded: list[list[dict[str, object]]] = []

        class FakeContext:
            async def add_cookies(self, cookies):
                recorded.append(cookies)

        await module.apply_session_seed_cookies(
            FakeContext(),
            {
                "seed_cookies": [
                    {
                        "name": "sid",
                        "value": "cookie",
                        "domain": ".taobao.com",
                        "path": "/",
                    }
                ]
            },
        )

        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0][0]["name"], "sid")

    async def test_apply_seed_storage_state_adds_cookies_and_init_script(self):
        module = importlib.import_module("domestic_browser")
        recorded_cookies: list[list[dict[str, object]]] = []
        recorded_scripts: list[str] = []

        class FakeContext:
            async def add_cookies(self, cookies):
                recorded_cookies.append(cookies)

            async def add_init_script(self, script):
                recorded_scripts.append(script)

        await module.apply_session_seed_storage_state(
            FakeContext(),
            {
                "seed_storage_state": {
                    "cookies": [
                        {
                            "name": "sid",
                            "value": "cookie",
                            "domain": ".taobao.com",
                            "path": "/",
                        }
                    ],
                    "origins": [
                        {
                            "origin": "https://www.xiaohongshu.com",
                            "localStorage": [{"name": "web_session", "value": "trusted-session"}],
                        }
                    ],
                }
            },
        )

        self.assertEqual(recorded_cookies[0][0]["domain"], ".taobao.com")
        self.assertIn("localStorage", recorded_scripts[0])
        self.assertIn("https://www.xiaohongshu.com", recorded_scripts[0])
        self.assertIn("web_session", recorded_scripts[0])


if __name__ == "__main__":
    unittest.main()
