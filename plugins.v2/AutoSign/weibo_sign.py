# -*- coding: utf-8 -*-
"""
微博超话自动签到模块
使用微博移动端 m.weibo.cn 接口
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
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
            "Referer": "https://m.weibo.cn/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "MWeibo-Pwa": "1",
            "X-Requested-With": "XMLHttpRequest",
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

    def get_followed_topics(self) -> List[Dict]:
        """
        获取关注的超话列表
        :return: 超话列表 [{id, name, level, is_sign, ...}]
        """
        topics = []
        try:
            # 使用微博移动端接口获取关注的超话
            since_id = ""
            page = 1
            while True:
                url = "https://m.weibo.cn/api/container/getIndex"
                params = {
                    "containerid": "100803_-_followsuper",
                }
                if since_id:
                    params["since_id"] = since_id

                resp = self.session.get(url, params=params, timeout=15)
                # 打印响应内容用于调试
                logger.debug(f"微博超话列表响应: {resp.text[:500]}")

                data = resp.json()

                if data.get("ok") != 1:
                    logger.warning(f"获取超话列表失败: {data.get('msg', '未知错误')}")
                    break

                cards = data.get("data", {}).get("cards", [])
                if not cards:
                    break

                # 解析卡片中的超话信息
                for card in cards:
                    card_group = card.get("card_group", [])
                    for item in card_group:
                        # 超话卡片
                        if item.get("card_type") == "8":
                            topic_id = item.get("itemid", "")
                            topic_name = item.get("title_sub", "") or item.get("title_sub", "")
                            # 从 scheme 中提取超话ID
                            scheme = item.get("scheme", "")
                            if not topic_id and "containerid=" in scheme:
                                match = re.search(r"containerid=(\d+)", scheme)
                                if match:
                                    topic_id = match.group(1)

                            # 检查签到状态
                            is_sign = False
                            btn_text = ""
                            # 查找按钮
                            buttons = item.get("buttons", [])
                            for btn in buttons:
                                btn_text = btn.get("title", "")
                                if btn_text == "已签到":
                                    is_sign = True
                                elif btn_text == "签到":
                                    is_sign = False

                            if topic_id and topic_name:
                                topics.append({
                                    "id": topic_id,
                                    "name": topic_name,
                                    "is_sign": is_sign,
                                    "btn_text": btn_text,
                                    "scheme": scheme,
                                })

                # 获取下一页的 since_id
                since_id = data.get("data", {}).get("cardlistInfo", {}).get("since_id", "")
                if not since_id:
                    break

                page += 1
                if page > 10:  # 最多获取10页
                    break
                time.sleep(1)

        except Exception as e:
            logger.error(f"获取微博超话列表失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

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
            # 先获取超话页面，找到签到按钮的 scheme
            url = "https://m.weibo.cn/api/container/getIndex"
            params = {
                "containerid": f"100808{topic_id}_-_super_index",
            }
            resp = self.session.get(url, params=params, timeout=15)
            data = resp.json()

            if data.get("ok") != 1:
                return {
                    "success": False,
                    "msg": f"获取超话信息失败: {data.get('msg', '未知错误')}",
                    "data": data,
                    "topic_name": topic_name,
                    "topic_id": topic_id,
                }

            # 查找签到按钮
            sign_scheme = ""
            cards = data.get("data", {}).get("cards", [])
            for card in cards:
                card_group = card.get("card_group", [])
                for item in card_group:
                    buttons = item.get("buttons", [])
                    for btn in buttons:
                        if btn.get("title") == "签到":
                            sign_scheme = btn.get("scheme", "")
                            break
                    if sign_scheme:
                        break
                if sign_scheme:
                    break

            if not sign_scheme:
                # 可能已经签到了
                return {
                    "success": True,
                    "msg": "已签到",
                    "data": {},
                    "topic_name": topic_name,
                    "topic_id": topic_id,
                }

            # 执行签到
            if sign_scheme.startswith("http"):
                sign_url = sign_scheme
            else:
                sign_url = f"https://m.weibo.cn{sign_scheme}"

            sign_resp = self.session.get(sign_url, timeout=15)
            sign_data = sign_resp.json()

            if sign_data.get("ok") == 1:
                return {
                    "success": True,
                    "msg": "签到成功",
                    "data": sign_data,
                    "topic_name": topic_name,
                    "topic_id": topic_id,
                }
            else:
                return {
                    "success": False,
                    "msg": sign_data.get("msg", "签到失败"),
                    "data": sign_data,
                    "topic_name": topic_name,
                    "topic_id": topic_id,
                }

        except Exception as e:
            logger.error(f"签到超话 {topic_name}({topic_id}) 失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
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

            # 如果已经签到了，跳过
            if topic.get("is_sign"):
                logger.info(f"  ✓ 已签到，跳过")
                results.append({
                    "success": True,
                    "msg": "已签到",
                    "topic_name": topic["name"],
                    "topic_id": topic["id"],
                })
            else:
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
            url = "https://m.weibo.cn/api/config"
            resp = self.session.get(url, timeout=10)
            data = resp.json()
            if data.get("data", {}).get("login"):
                return True
            return False
        except Exception as e:
            logger.error(f"检查微博登录状态失败: {str(e)}")
            return False
