# -*- coding: utf-8 -*-
"""
微博超话自动签到模块
"""
import requests
import time
import re
from typing import List, Dict, Optional
from app.log import logger


class WeiboSuperTopicSign:
    """微博超话签到类"""

    def __init__(self, cookie: str):
        """
        初始化
        :param cookie: 微博 Cookie
        """
        self.cookie = cookie.strip()
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Weibo (iPhone;9,3;Scale/3.00)",
            "Referer": "https://weibo.com/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        self.session.headers.update(self.headers)
        # 设置 Cookie
        self._set_cookie()

    def _set_cookie(self):
        """设置 Cookie"""
        if not self.cookie:
            return
        # 解析 Cookie 字符串
        cookies = {}
        for item in self.cookie.split(";"):
            item = item.strip()
            if "=" in item:
                key, value = item.split("=", 1)
                cookies[key.strip()] = value.strip()
        self.session.cookies.update(cookies)

    def _get_tbs(self) -> str:
        """获取 tbs 参数"""
        try:
            url = "http://tieba.baidu.com/dc/common/tbs"
            resp = self.session.get(url, timeout=10)
            data = resp.json()
            return data.get("tbs", "")
        except Exception as e:
            logger.error(f"获取微博 tbs 失败: {str(e)}")
            return ""

    def get_followed_topics(self) -> List[Dict]:
        """
        获取关注的超话列表
        :return: 超话列表 [{id, name, level, ...}]
        """
        topics = []
        try:
            # 使用移动端接口获取关注的超话
            page = 1
            while True:
                url = f"https://weibo.com/p/aj/v6/mblog/mbloglist"
                params = {
                    "ajwvr": "6",
                    "id": "100803_-_follow",
                    "page": page,
                    "pagebar": "0",
                    "tab": "super_index",
                    "pl_name": "Pl_Core_MixedFeed__24",
                    "idflag": "2",
                    "domain": "100803",
                    "domain_op": "100803",
                    "feed_type": "1",
                    "pre_page": page,
                    "end_id": "",
                    "end_idcard": "",
                    "end_mark": "",
                    "start_id": "",
                    "start_idcard": "",
                    "start_mark": "",
                    "yulu_video": "0",
                    "feed_type_v": "feedlike",
                    "is_qxkb": "0",
                }
                resp = self.session.get(url, params=params, timeout=10)
                data = resp.json()

                if data.get("code") != "100000":
                    break

                html = data.get("data", "")
                if not html:
                    break

                # 解析 HTML 提取超话信息
                # 匹配超话ID和名称
                pattern = r'href="https://weibo\.com/p/(\d+)/super_index"\s+title="([^"]+)"'
                matches = re.findall(pattern, html)

                if not matches:
                    break

                for topic_id, topic_name in matches:
                    if topic_id and topic_name:
                        topics.append({
                            "id": topic_id,
                            "name": topic_name,
                        })

                page += 1
                if page > 10:  # 最多获取10页
                    break

                time.sleep(1)

        except Exception as e:
            logger.error(f"获取微博超话列表失败: {str(e)}")

        # 去重
        seen = set()
        unique_topics = []
        for topic in topics:
            if topic["id"] not in seen:
                seen.add(topic["id"])
                unique_topics.append(topic)

        logger.info(f"获取到 {len(unique_topics)} 个关注的超话")
        return unique_topics

    def sign_topic(self, topic_id: str, topic_name: str = "") -> Dict:
        """
        签到单个超话
        :param topic_id: 超话ID
        :param topic_name: 超话名称（用于日志）
        :return: 签到结果 {success, msg, data}
        """
        try:
            url = "https://weibo.com/p/aj/general/button"
            params = {
                "ajwvr": "6",
                "api": "http://i.huati.weibo.com/aj/super/checkin",
                "id": topic_id,
                "location": "page_100808_super_index",
                "timezone": "GMT+0800",
                "lang": "zh-cn",
                "plat": "MacIntel",
                "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "screen": "2560*1440",
                "__rnd": str(int(time.time() * 1000)),
            }

            resp = self.session.get(url, params=params, timeout=10)
            result = resp.json()

            if result.get("code") == "100000":
                data = result.get("data", {})
                return {
                    "success": True,
                    "msg": data.get("msg", "签到成功"),
                    "data": data,
                    "topic_name": topic_name,
                    "topic_id": topic_id,
                }
            else:
                return {
                    "success": False,
                    "msg": result.get("msg", "签到失败"),
                    "data": result,
                    "topic_name": topic_name,
                    "topic_id": topic_id,
                }

        except Exception as e:
            logger.error(f"签到超话 {topic_name}({topic_id}) 失败: {str(e)}")
            return {
                "success": False,
                "msg": f"签到异常: {str(e)}",
                "data": {},
                "topic_name": topic_name,
                "topic_id": topic_id,
            }

    def sign_all(self, delay: int = 2) -> List[Dict]:
        """
        签到所有关注的超话
        :param delay: 每个签到之间的延迟（秒）
        :return: 签到结果列表
        """
        results = []
        topics = self.get_followed_topics()

        if not topics:
            logger.warning("未获取到关注的超话列表")
            return results

        logger.info(f"开始签到 {len(topics)} 个超话...")

        for i, topic in enumerate(topics, 1):
            logger.info(f"[{i}/{len(topics)}] 正在签到: {topic['name']}")
            result = self.sign_topic(topic["id"], topic["name"])
            results.append(result)

            status = "✓" if result["success"] else "✗"
            logger.info(f"  {status} {result['msg']}")

            if i < len(topics):
                time.sleep(delay)

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
            url = "https://weibo.com/ajax/profile/info"
            resp = self.session.get(url, timeout=10)
            data = resp.json()
            if data.get("ok") == 1:
                return True
            return False
        except Exception as e:
            logger.error(f"检查微博登录状态失败: {str(e)}")
            return False
