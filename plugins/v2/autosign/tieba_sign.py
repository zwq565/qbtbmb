# -*- coding: utf-8 -*-
"""
贴吧自动签到模块
"""
import requests
import time
import hashlib
from typing import List, Dict, Optional
from app.log import logger


class TiebaSign:
    """贴吧签到类"""

    def __init__(self, bduss: str, stoken: str = ""):
        """
        初始化
        :param bduss: 百度 BDUSS Cookie
        :param stoken: 百度 STOKEN Cookie（可选）
        """
        self.bduss = bduss.strip()
        self.stoken = stoken.strip()
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://tieba.baidu.com/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        self.session.headers.update(self.headers)
        # 设置 Cookie
        self._set_cookie()

    def _set_cookie(self):
        """设置 Cookie"""
        if self.bduss:
            self.session.cookies.set("BDUSS", self.bduss, domain=".baidu.com")
        if self.stoken:
            self.session.cookies.set("STOKEN", self.stoken, domain=".baidu.com")

    def get_tbs(self) -> str:
        """
        获取 tbs 参数（贴吧的防篡改标识）
        :return: tbs 字符串
        """
        try:
            url = "http://tieba.baidu.com/dc/common/tbs"
            resp = self.session.get(url, timeout=10)
            data = resp.json()
            return data.get("tbs", "")
        except Exception as e:
            logger.error(f"获取贴吧 tbs 失败: {str(e)}")
            return ""

    def get_liked_forums(self) -> List[Dict]:
        """
        获取关注的贴吧列表
        :return: 贴吧列表 [{name, fid, level, is_sign, ...}]
        """
        forums = []
        try:
            page = 1
            while True:
                url = f"https://tieba.baidu.com/mo/q/newmoindex?pn={page}"
                resp = self.session.get(url, timeout=10)
                data = resp.json()

                if data.get("no") != 0:
                    break

                like_forum = data.get("data", {}).get("like_forum", [])
                if not like_forum:
                    break

                for forum in like_forum:
                    forums.append({
                        "name": forum.get("name", ""),
                        "fid": forum.get("id", ""),
                        "level": forum.get("level", 0),
                        "level_id": forum.get("level_id", 0),
                        "is_sign": forum.get("is_sign", 0) == 1,
                        "user_sign_rank": forum.get("user_sign_rank", 0),
                        "cont_sign_num": forum.get("cont_sign_num", 0),
                        "total_sign_num": forum.get("total_sign_num", 0),
                    })

                page += 1
                if page > 20:  # 最多获取20页
                    break

                time.sleep(0.5)

        except Exception as e:
            logger.error(f"获取关注贴吧列表失败: {str(e)}")

        logger.info(f"获取到 {len(forums)} 个关注的贴吧")
        return forums

    def sign_one(self, forum_name: str, tbs: str = "") -> Dict:
        """
        签到单个贴吧
        :param forum_name: 贴吧名称
        :param tbs: tbs 参数（为空则自动获取）
        :return: 签到结果 {success, msg, data}
        """
        try:
            if not tbs:
                tbs = self.get_tbs()

            if not tbs:
                return {
                    "success": False,
                    "msg": "获取 tbs 失败",
                    "data": {},
                    "forum_name": forum_name,
                }

            url = "http://tieba.baidu.com/sign/add"
            data = {
                "ie": "utf-8",
                "kw": forum_name,
                "tbs": tbs,
            }

            resp = self.session.post(url, data=data, timeout=10)
            result = resp.json()

            if result.get("no") == 0:
                # 签到成功
                sign_data = result.get("data", {})
                return {
                    "success": True,
                    "msg": "签到成功",
                    "data": sign_data,
                    "forum_name": forum_name,
                    "exp": sign_data.get("exp", 0),
                    "rank": sign_data.get("rank", 0),
                }
            elif result.get("no") == 1101:
                # 已经签到过了
                return {
                    "success": True,
                    "msg": "已经签到过了",
                    "data": result.get("data", {}),
                    "forum_name": forum_name,
                }
            else:
                # 签到失败
                return {
                    "success": False,
                    "msg": result.get("error", f"签到失败 (错误码: {result.get('no')})"),
                    "data": result,
                    "forum_name": forum_name,
                }

        except Exception as e:
            logger.error(f"签到贴吧 {forum_name} 失败: {str(e)}")
            return {
                "success": False,
                "msg": f"签到异常: {str(e)}",
                "data": {},
                "forum_name": forum_name,
            }

    def onekey_sign(self) -> Dict:
        """
        一键签到（VIP 功能，可签到 7 级以上贴吧）
        注意：百度贴吧 0 点到 1 点不能够使用一键签到
        :return: 一键签到结果
        """
        try:
            tbs = self.get_tbs()
            if not tbs:
                return {
                    "success": False,
                    "msg": "获取 tbs 失败",
                    "data": {},
                }

            url = "https://tieba.baidu.com/tbmall/onekeySignin1"
            data = {
                "ie": "utf-8",
                "tbs": tbs,
            }

            resp = self.session.post(url, data=data, timeout=10)
            result = resp.json()

            if result.get("no") == 0:
                return {
                    "success": True,
                    "msg": "一键签到成功",
                    "data": result.get("data", {}),
                }
            else:
                return {
                    "success": False,
                    "msg": result.get("error", f"一键签到失败 (错误码: {result.get('no')})"),
                    "data": result,
                }

        except Exception as e:
            logger.error(f"一键签到失败: {str(e)}")
            return {
                "success": False,
                "msg": f"一键签到异常: {str(e)}",
                "data": {},
            }

    def sign_all(self, delay: float = 1.5, use_onekey: bool = True) -> List[Dict]:
        """
        签到所有关注的贴吧
        :param delay: 每个签到之间的延迟（秒）
        :param use_onekey: 是否优先使用一键签到
        :return: 签到结果列表
        """
        results = []
        forums = self.get_liked_forums()

        if not forums:
            logger.warning("未获取到关注的贴吧列表")
            return results

        logger.info(f"开始签到 {len(forums)} 个贴吧...")

        # 先尝试一键签到（如果开启）
        if use_onekey:
            logger.info("尝试使用一键签到...")
            onekey_result = self.onekey_sign()
            if onekey_result["success"]:
                logger.info("一键签到成功，正在验证签到状态...")
                # 重新获取贴吧列表，检查签到状态
                time.sleep(2)
                forums = self.get_liked_forums()

        # 逐个签到未签到的贴吧
        tbs = self.get_tbs()
        unsigned_forums = [f for f in forums if not f["is_sign"]]

        logger.info(f"需要逐个签到的贴吧: {len(unsigned_forums)} 个")

        for i, forum in enumerate(unsigned_forums, 1):
            logger.info(f"[{i}/{len(unsigned_forums)}] 正在签到: {forum['name']}")
            result = self.sign_one(forum["name"], tbs)
            results.append(result)

            status = "✓" if result["success"] else "✗"
            logger.info(f"  {status} {result['msg']}")

            if i < len(unsigned_forums):
                time.sleep(delay)

        # 加上已经签到的
        signed_forums = [f for f in forums if f["is_sign"]]
        for forum in signed_forums:
            results.append({
                "success": True,
                "msg": "已签到",
                "data": {},
                "forum_name": forum["name"],
            })

        # 统计
        success_count = sum(1 for r in results if r["success"])
        fail_count = len(results) - success_count
        logger.info(f"签到完成: 成功 {success_count} 个，失败 {fail_count} 个")

        return results

    def check_login(self) -> bool:
        """
        检查是否登录有效
        :return: True/False
        """
        try:
            tbs = self.get_tbs()
            return bool(tbs)
        except Exception as e:
            logger.error(f"检查贴吧登录状态失败: {str(e)}")
            return False
