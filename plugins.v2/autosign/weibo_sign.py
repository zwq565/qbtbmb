# -*- coding: utf-8 -*-
"""
微博超话自动签到模块
使用微博移动端 m.weibo.cn 接口
优化版：更完整的请求头，更好的错误处理
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

        # 更完整的移动端请求头，模拟 iPhone Safari
        self.headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh-Hans;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://m.weibo.cn/",
            "MWeibo-Pwa": "1",
            "X-Requested-With": "XMLHttpRequest",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        self.session.headers.update(self.headers)
        self._set_cookie()

    def _set_cookie(self):
        """设置 Cookie"""
        if not self.cookie:
            return
        try:
            # 解析 Cookie 字符串
            cookies = {}
            for item in self.cookie.split(";"):
                item = item.strip()
                if "=" in item:
                    key, value = item.split("=", 1)
                    cookies[key.strip()] = value.strip()
            self.session.cookies.update(cookies)
            logger.info(f"微博 Cookie 解析成功，共 {len(cookies)} 个字段")
        except Exception as e:
            logger.error(f"微博 Cookie 解析失败: {str(e)}")

    def check_login(self) -> bool:
        """
        检查登录状态
        :return: 是否已登录
        """
        try:
            url = "https://m.weibo.cn/api/config"
            resp = self.session.get(url, timeout=15)
            data = resp.json()
            is_login = data.get("data", {}).get("login", False)
            logger.info(f"微博登录状态检查: {'已登录' if is_login else '未登录'}")
            return is_login
        except Exception as e:
            logger.error(f"检查微博登录状态失败: {str(e)}")
            return False

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

                logger.debug(f"获取超话列表，第 {page} 页")
                resp = self.session.get(url, params=params, timeout=15)

                # 检查响应状态
                if resp.status_code != 200:
                    logger.error(f"获取超话列表失败，HTTP 状态码: {resp.status_code}")
                    break

                try:
                    data = resp.json()
                except Exception as e:
                    logger.error(f"超话列表 JSON 解析失败: {str(e)}")
                    logger.debug(f"响应内容: {resp.text[:500]}")
                    break

                # 检查返回码
                ok = data.get("ok", 0)
                if ok == -100:
                    # 需要登录验证或验证码
                    errno = data.get("errno", "")
                    logger.error(f"微博返回 -100 错误，需要验证。errno: {errno}")
                    logger.error("可能原因：Cookie 无效、过期，或需要验证码验证")
                    logger.error("建议：重新从 m.weibo.cn 获取 Cookie")
                    break
                elif ok != 1:
                    msg = data.get("msg", "未知错误")
                    logger.error(f"获取超话列表失败: {msg}")
                    break

                cards = data.get("data", {}).get("cards", [])
                for card in cards:
                    card_group = card.get("card_group", [])
                    for item in card_group:
                        if item.get("card_type") == 8:
                            # 超话卡片
                            topic_id = item.get("itemid", "")
                            topic_name = item.get("title_sub", "")
                            level = item.get("desc1", "")
                            is_sign = False
                            sign_btn = None

                            # 检查签到状态
                            buttons = item.get("buttons", [])
                            for btn in buttons:
                                if btn.get("title") == "已签到":
                                    is_sign = True
                                elif btn.get("title") == "签到":
                                    sign_btn = btn

                            if topic_id and topic_name:
                                topics.append({
                                    "id": topic_id,
                                    "name": topic_name,
                                    "level": level,
                                    "is_sign": is_sign,
                                    "sign_btn": sign_btn,
                                    "raw": item,
                                })

                # 获取下一页
                since_id = data.get("data", {}).get("cardlistInfo", {}).get("since_id", "")
                if not since_id:
                    break

                page += 1
                if page > 10:
                    logger.warning("超话列表超过 10 页，停止获取")
                    break

                time.sleep(1)

        except Exception as e:
            logger.error(f"获取微博超话列表失败: {str(e)}")
            import traceback
            logger.debug(traceback.format_exc())

        # 去重
        unique_topics = []
        seen_ids = set()
        for topic in topics:
            if topic["id"] not in seen_ids:
                seen_ids.add(topic["id"])
                unique_topics.append(topic)

        logger.info(f"获取到 {len(unique_topics)} 个关注的超话")
        return unique_topics

    def sign_topic(self, topic_id: str, topic_name: str = "") -> Dict:
        """
        签到单个超话
        :param topic_id: 超话 ID
        :param topic_name: 超话名称
        :return: 签到结果 {success, msg, data}
        """
        result = {
            "success": False,
            "msg": "",
            "data": None,
            "topic_id": topic_id,
            "topic_name": topic_name,
        }

        try:
            # 先获取超话页面，找到签到按钮
            url = "https://m.weibo.cn/api/container/getIndex"
            params = {
                "containerid": f"100808{topic_id}_-_super_index",
            }
            resp = self.session.get(url, params=params, timeout=15)
            data = resp.json()

            if data.get("ok") != 1:
                result["msg"] = f"获取超话页面失败: {data.get('msg', '未知错误')}"
                return result

            # 查找签到按钮
            cards = data.get("data", {}).get("cards", [])
            sign_scheme = None
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
                result["success"] = True
                result["msg"] = "已签到"
                return result

            # 执行签到
            sign_url = f"https://m.weibo.cn{sign_scheme}"
            sign_resp = self.session.get(sign_url, timeout=15)
            sign_data = sign_resp.json()

            if sign_data.get("ok") == 1:
                result["success"] = True
                result["msg"] = "签到成功"
                result["data"] = sign_data.get("data")
            else:
                result["msg"] = sign_data.get("msg", "签到失败")

        except Exception as e:
            result["msg"] = f"签到异常: {str(e)}"
            logger.error(f"超话 {topic_name} 签到失败: {str(e)}")

        return result

    def sign_all(self, delay: float = 2.0) -> List[Dict]:
        """
        签到所有关注的超话
        :param delay: 每个超话签到间隔（秒）
        :return: 签到结果列表
        """
        results = []

        # 先检查登录状态
        if not self.check_login():
            logger.error("微博未登录，请检查 Cookie 是否有效")
            results.append({
                "success": False,
                "msg": "未登录，Cookie 无效或已过期",
                "topic_name": "登录检查",
                "topic_id": "",
            })
            return results

        # 获取关注的超话列表
        topics = self.get_followed_topics()
        if not topics:
            logger.warning("未获取到关注的超话列表")
            return results

        logger.info(f"开始签到 {len(topics)} 个超话")

        for i, topic in enumerate(topics):
            topic_name = topic.get("name", "")
            topic_id = topic.get("id", "")

            # 跳过已签到的
            if topic.get("is_sign"):
                logger.info(f"[{i+1}/{len(topics)}] {topic_name} - 已签到，跳过")
                results.append({
                    "success": True,
                    "msg": "已签到",
                    "topic_name": topic_name,
                    "topic_id": topic_id,
                })
                continue

            # 执行签到
            logger.info(f"[{i+1}/{len(topics)}] 正在签到: {topic_name}")
            result = self.sign_topic(topic_id, topic_name)
            results.append(result)

            if result["success"]:
                logger.info(f"[{i+1}/{len(topics)}] {topic_name} - 签到成功")
            else:
                logger.warning(f"[{i+1}/{len(topics)}] {topic_name} - {result['msg']}")

            # 延迟
            if i < len(topics) - 1:
                time.sleep(delay)

        # 统计
        success_count = sum(1 for r in results if r["success"])
        logger.info(f"超话签到完成: 成功 {success_count}/{len(results)}")

        return results
