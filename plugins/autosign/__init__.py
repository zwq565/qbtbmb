# -*- coding: utf-8 -*-
"""
MoviePilot 自动签到插件
支持贴吧和微博超话自动签到
"""
import os
import time
import json
import threading
from datetime import datetime
from typing import Any, List, Dict, Tuple, Optional

from app.plugins import _PluginBase
from app.log import logger
from app.schemas import NotificationType
from app.core.config import settings


class AutoSign(_PluginBase):
    """自动签到插件主类"""

    # 插件名称
    plugin_name = "自动签到 v1.0.7"
    # 插件描述
    plugin_desc = "自动签到贴吧和微博超话，支持定时任务和结果通知"
    # 插件版本
    plugin_version = "1.0.7"
    # 插件作者
    plugin_author = "MoviePilot Community"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/docs/icons/autosign.png"
    # 插件主题色
    plugin_color = "#FF6B6B"
    # 插件配置项
    plugin_config = {}
    # 插件配置模板
    plugin_config_template = {
        "enable": {
            "type": "switch",
            "title": "启用插件",
            "default": True,
        },
        "sign_time": {
            "type": "text",
            "title": "签到时间",
            "default": "08:00",
            "placeholder": "例如：08:00",
            "description": "每天自动签到的时间，24小时制",
        },
        "tieba_enable": {
            "type": "switch",
            "title": "启用贴吧签到",
            "default": True,
        },
        "tieba_bduss": {
            "type": "text",
            "title": "贴吧 BDUSS",
            "default": "",
            "placeholder": "请输入百度 BDUSS Cookie",
            "description": "从浏览器 Cookie 中获取 BDUSS 值",
        },
        "tieba_stoken": {
            "type": "text",
            "title": "贴吧 STOKEN",
            "default": "",
            "placeholder": "请输入百度 STOKEN Cookie（可选）",
            "description": "从浏览器 Cookie 中获取 STOKEN 值（可选）",
        },
        "tieba_use_onekey": {
            "type": "switch",
            "title": "优先使用一键签到",
            "default": True,
            "description": "优先使用贴吧一键签到功能（VIP功能，7级以上贴吧）",
        },
        "tieba_delay": {
            "type": "number",
            "title": "贴吧签到间隔(秒)",
            "default": 1.5,
            "min": 0.5,
            "max": 10,
            "description": "每个贴吧签到之间的延迟，避免请求过快",
        },
        "weibo_enable": {
            "type": "switch",
            "title": "启用微博超话签到",
            "default": False,
        },
        "weibo_cookie": {
            "type": "text",
            "title": "微博 Cookie",
            "default": "",
            "placeholder": "请输入微博完整 Cookie",
            "description": "从浏览器中复制完整的微博 Cookie",
        },
        "weibo_delay": {
            "type": "number",
            "title": "微博签到间隔(秒)",
            "default": 2,
            "min": 1,
            "max": 10,
            "description": "每个超话签到之间的延迟，避免请求过快",
        },
        "notify_enable": {
            "type": "switch",
            "title": "启用签到结果通知",
            "default": True,
        },
        "notify_only_fail": {
            "type": "switch",
            "title": "仅失败时通知",
            "default": False,
            "description": "只有签到失败时才发送通知",
        },
    }

    # 定时任务线程
    _scheduler_thread = None
    _stop_event = None
    _last_sign_time = None
    _last_sign_result = None
    _first_run = True

    def init_plugin(self, config: dict = None):
        """
        插件初始化
        :param config: 插件配置
        """
        if config:
            self.plugin_config = config

        logger.info(f"[{self.plugin_name}] 插件初始化")
        logger.info(f"[{self.plugin_name}] 当前配置: sign_time={self.plugin_config.get('sign_time')}, tieba_enable={self.plugin_config.get('tieba_enable')}, weibo_enable={self.plugin_config.get('weibo_enable')}")

        # 启用插件时启动定时任务
        if self.plugin_config.get("enable", True):
            self._start_scheduler()
        else:
            logger.info(f"[{self.plugin_name}] 插件未启用，停止定时任务")
            self.stop_service()

    def _start_scheduler(self):
        """
        启动定时签到任务
        """
        # 如果已有定时任务在运行，先停止
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            logger.info(f"[{self.plugin_name}] 重启定时任务")
            if self._stop_event:
                self._stop_event.set()
            self._scheduler_thread.join(timeout=5)

        self._stop_event = threading.Event()
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            name="AutoSign-Scheduler",
            daemon=True,
        )
        self._scheduler_thread.start()
        logger.info(f"[{self.plugin_name}] 定时签到任务已启动")

    def _scheduler_loop(self):
        """
        定时任务循环
        """
        logger.info(f"[{self.plugin_name}] 定时任务循环已启动")

        while not self._stop_event.is_set():
            try:
                # 每次循环都重新读取配置，确保修改后立即生效
                sign_time = self.plugin_config.get("sign_time", "08:00")
                now = datetime.now()

                # 解析签到时间
                try:
                    sign_hour, sign_minute = map(int, sign_time.split(":"))
                except Exception:
                    sign_hour, sign_minute = 8, 0

                current_hour = now.hour
                current_minute = now.minute

                # 判断是否到了签到时间（宽松判断：当前时间 >= 签到时间，且今天还没签到过）
                should_sign = False
                if current_hour > sign_hour:
                    should_sign = True
                elif current_hour == sign_hour and current_minute >= sign_minute:
                    should_sign = True

                if should_sign:
                    # 第一次运行时，只要时间到了就签到（方便测试）
                    # 之后按天判断，一天只签到一次
                    if (
                        self._first_run
                        or self._last_sign_time is None
                        or self._last_sign_time.date() != now.date()
                    ):
                        logger.info(f"[{self.plugin_name}] 到达签到时间({sign_time})，开始执行签到")
                        try:
                            self._do_sign()
                            self._last_sign_time = now
                            self._first_run = False
                            logger.info(f"[{self.plugin_name}] 签到完成")
                        except Exception as e:
                            logger.error(f"[{self.plugin_name}] 签到执行失败: {str(e)}")
                            import traceback
                            logger.error(traceback.format_exc())

                # 每分钟检查一次
                time.sleep(60)

            except Exception as e:
                logger.error(f"[{self.plugin_name}] 定时任务异常: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                time.sleep(60)

    def _do_sign(self) -> Dict:
        """
        执行签到
        :return: 签到结果
        """
        results = {
            "tieba": {"success": 0, "total": 0, "details": []},
            "weibo": {"success": 0, "total": 0, "details": []},
            "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # 贴吧签到
        if self.plugin_config.get("tieba_enable", True):
            logger.info(f"[{self.plugin_name}] 开始贴吧签到")
            try:
                from .tieba_sign import TiebaSign

                bduss = self.plugin_config.get("tieba_bduss", "")
                stoken = self.plugin_config.get("tieba_stoken", "")
                use_onekey = self.plugin_config.get("tieba_use_onekey", True)
                delay = self.plugin_config.get("tieba_delay", 1.5)

                if bduss:
                    tieba = TiebaSign(bduss, stoken)
                    tieba_results = tieba.sign_all(delay=delay, use_onekey=use_onekey)

                    results["tieba"]["total"] = len(tieba_results)
                    results["tieba"]["success"] = sum(
                        1 for r in tieba_results if r["success"]
                    )
                    results["tieba"]["details"] = tieba_results
                else:
                    logger.warning(f"[{self.plugin_name}] 贴吧 BDUSS 未配置，跳过签到")

            except Exception as e:
                logger.error(f"[{self.plugin_name}] 贴吧签到异常: {str(e)}")
                results["tieba"]["error"] = str(e)

        # 微博超话签到
        if self.plugin_config.get("weibo_enable", False):
            logger.info(f"[{self.plugin_name}] 开始微博超话签到")
            try:
                from .weibo_sign import WeiboSuperTopicSign

                cookie = self.plugin_config.get("weibo_cookie", "")
                delay = self.plugin_config.get("weibo_delay", 2)

                if cookie:
                    weibo = WeiboSuperTopicSign(cookie)
                    weibo_results = weibo.sign_all(delay=delay)

                    results["weibo"]["total"] = len(weibo_results)
                    results["weibo"]["success"] = sum(
                        1 for r in weibo_results if r["success"]
                    )
                    results["weibo"]["details"] = weibo_results
                else:
                    logger.warning(f"[{self.plugin_name}] 微博 Cookie 未配置，跳过签到")

            except Exception as e:
                logger.error(f"[{self.plugin_name}] 微博超话签到异常: {str(e)}")
                results["weibo"]["error"] = str(e)

        results["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._last_sign_result = results

        # 保存签到结果到配置，方便用户通过「查看数据」查看
        self.plugin_config["_last_result"] = results
        self.plugin_config["_last_sign_time"] = results["start_time"]

        # 发送通知
        if self.plugin_config.get("notify_enable", True):
            self._send_notification(results)

        logger.info(f"[{self.plugin_name}] 签到完成")
        return results

    def _send_notification(self, results: Dict):
        """
        发送签到结果通知
        :param results: 签到结果
        """
        try:
            # 检查是否仅失败时通知
            only_fail = self.plugin_config.get("notify_only_fail", False)
            if only_fail:
                # 检查是否有失败
                tieba_fail = (
                    results["tieba"]["total"] - results["tieba"]["success"]
                )
                weibo_fail = (
                    results["weibo"]["total"] - results["weibo"]["success"]
                )
                if tieba_fail == 0 and weibo_fail == 0:
                    logger.info(f"[{self.plugin_name}] 全部签到成功，跳过通知")
                    return

            # 构建通知消息
            title = "📋 自动签到结果"
            message = f"签到时间: {results['start_time']}\n\n"

            if self.plugin_config.get("tieba_enable", True):
                tieba = results["tieba"]
                message += f"【贴吧签到】\n"
                message += f"成功: {tieba['success']}/{tieba['total']}\n"
                if tieba.get("details"):
                    # 只显示失败的
                    fail_details = [
                        d for d in tieba["details"] if not d["success"]
                    ]
                    if fail_details:
                        message += "失败列表:\n"
                        for d in fail_details[:5]:  # 最多显示5个
                            message += f"  - {d['forum_name']}: {d['msg']}\n"
                        if len(fail_details) > 5:
                            message += f"  ... 还有 {len(fail_details) - 5} 个\n"
                message += "\n"

            if self.plugin_config.get("weibo_enable", False):
                weibo = results["weibo"]
                message += f"【微博超话签到】\n"
                message += f"成功: {weibo['success']}/{weibo['total']}\n"
                if weibo.get("details"):
                    fail_details = [
                        d for d in weibo["details"] if not d["success"]
                    ]
                    if fail_details:
                        message += "失败列表:\n"
                        for d in fail_details[:5]:
                            message += f"  - {d['topic_name']}: {d['msg']}\n"
                        if len(fail_details) > 5:
                            message += f"  ... 还有 {len(fail_details) - 5} 个\n"
                message += "\n"

            # 发送通知
            if hasattr(settings, "post_message"):
                settings.post_message(
                    mtype=NotificationType.Plugin,
                    title=title,
                    text=message,
                )
            else:
                # 备用通知方式
                logger.info(f"[{self.plugin_name}] 通知: {title}\n{message}")

        except Exception as e:
            logger.error(f"[{self.plugin_name}] 发送通知失败: {str(e)}")

    def get_state(self) -> Tuple[bool, str]:
        """
        获取插件状态
        :return: (是否启用, 状态描述)
        """
        enable = self.plugin_config.get("enable", True)
        if not enable:
            return False, "未启用"

        if self._last_sign_time:
            status = f"上次签到: {self._last_sign_time.strftime('%Y-%m-%d %H:%M:%S')}"
            if self._last_sign_result:
                tieba_ok = self._last_sign_result["tieba"]["success"]
                tieba_total = self._last_sign_result["tieba"]["total"]
                weibo_ok = self._last_sign_result["weibo"]["success"]
                weibo_total = self._last_sign_result["weibo"]["total"]
                status += f" (贴吧 {tieba_ok}/{tieba_total}"
                if self.plugin_config.get("weibo_enable", False):
                    status += f", 微博 {weibo_ok}/{weibo_total}"
                status += ")"
            return True, status
        else:
            return True, "等待签到"

    def get_api(self) -> List[Dict[str, Any]]:
        """
        注册 API 接口
        """
        return [
            {
                "path": "/sign_now",
                "method": "POST",
                "endpoint": self.api_sign_now,
                "summary": "立即执行签到",
                "description": "手动触发立即执行签到任务",
            },
            {
                "path": "/sign_result",
                "method": "GET",
                "endpoint": self.api_sign_result,
                "summary": "获取上次签到结果",
                "description": "获取最近一次签到的详细结果",
            },
            {
                "path": "/check_tieba",
                "method": "GET",
                "endpoint": self.api_check_tieba,
                "summary": "测试贴吧连接",
                "description": "测试贴吧 BDUSS 是否有效",
            },
            {
                "path": "/check_weibo",
                "method": "GET",
                "endpoint": self.api_check_weibo,
                "summary": "测试微博连接",
                "description": "测试微博 Cookie 是否有效",
            },
        ]

    def api_sign_now(self, request: Any) -> Dict:
        """
        API: 立即执行签到
        """
        logger.info(f"[{self.plugin_name}] API 触发立即签到")
        result = self._do_sign()
        return {
            "code": 0,
            "msg": "签到完成",
            "data": result,
        }

    def api_sign_result(self, request: Any) -> Dict:
        """
        API: 获取上次签到结果
        """
        return {
            "code": 0,
            "msg": "success",
            "data": {
                "last_sign_time": self._last_sign_time.strftime("%Y-%m-%d %H:%M:%S")
                if self._last_sign_time
                else None,
                "result": self._last_sign_result,
            },
        }

    def api_check_tieba(self, request: Any) -> Dict:
        """
        API: 测试贴吧连接
        """
        try:
            from .tieba_sign import TiebaSign

            bduss = self.plugin_config.get("tieba_bduss", "")
            if not bduss:
                return {"code": 1, "msg": "BDUSS 未配置"}

            tieba = TiebaSign(bduss)
            if tieba.check_login():
                return {"code": 0, "msg": "贴吧连接正常"}
            else:
                return {"code": 1, "msg": "贴吧连接失败，请检查 BDUSS 是否有效"}
        except Exception as e:
            return {"code": 1, "msg": f"测试失败: {str(e)}"}

    def api_check_weibo(self, request: Any) -> Dict:
        """
        API: 测试微博连接
        """
        try:
            from .weibo_sign import WeiboSuperTopicSign

            cookie = self.plugin_config.get("weibo_cookie", "")
            if not cookie:
                return {"code": 1, "msg": "Cookie 未配置"}

            weibo = WeiboSuperTopicSign(cookie)
            if weibo.check_login():
                return {"code": 0, "msg": "微博连接正常"}
            else:
                return {"code": 1, "msg": "微博连接失败，请检查 Cookie 是否有效"}
        except Exception as e:
            return {"code": 1, "msg": f"测试失败: {str(e)}"}

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册服务
        """
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        配置表单
        :return: (表单配置, 默认值)
        """
        # 简化版：直接平铺组件，不用 VCard 分组
        form = [
            {
                "component": "v-btn",
                "props": {
                    "label": "🚀 立即执行签到",
                    "color": "primary",
                    "block": True,
                    "variant": "flat",
                },
                "action": {
                    "api": "/sign_now",
                    "method": "POST",
                    "message": "签到任务已开始执行，请查看日志",
                },
            },
            {
                "component": "v-switch",
                "props": {
                    "label": "启用插件",
                    "model": "enable",
                },
            },
            {
                "component": "v-text-field",
                "props": {
                    "label": "每日签到时间",
                    "model": "sign_time",
                    "placeholder": "08:00",
                },
            },
            {
                "component": "v-switch",
                "props": {
                    "label": "启用贴吧签到",
                    "model": "tieba_enable",
                },
            },
            {
                "component": "v-text-field",
                "props": {
                    "label": "贴吧 BDUSS",
                    "model": "tieba_bduss",
                    "placeholder": "请输入百度 BDUSS",
                    "type": "password",
                },
            },
            {
                "component": "v-switch",
                "props": {
                    "label": "启用微博超话签到",
                    "model": "weibo_enable",
                },
            },
            {
                "component": "v-textarea",
                "props": {
                    "label": "微博 Cookie",
                    "model": "weibo_cookie",
                    "placeholder": "请输入微博完整 Cookie",
                    "rows": 3,
                },
            },
            {
                "component": "v-switch",
                "props": {
                    "label": "启用签到结果通知",
                    "model": "notify_enable",
                },
            },
        ]

        # 默认值
        defaults = {
            "enable": True,
            "sign_time": "08:00",
            "tieba_enable": True,
            "tieba_bduss": "",
            "tieba_stoken": "",
            "tieba_use_onekey": True,
            "tieba_delay": 1.5,
            "weibo_enable": False,
            "weibo_cookie": "",
            "weibo_delay": 2,
            "notify_enable": True,
            "notify_only_fail": False,
        }

        # 合并当前配置
        for key, value in self.plugin_config.items():
            if key in defaults:
                defaults[key] = value

        return form, defaults

    def get_page(self) -> List[dict]:
        """
        插件页面
        """
        return [
            {
                "title": "立即签到",
                "path": "/sign_now",
                "component": "AutoSignPage",
            }
        ]

    def stop_service(self):
        """
        停止插件
        """
        logger.info(f"[{self.plugin_name}] 停止插件服务")
        if self._stop_event:
            self._stop_event.set()
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5)
        logger.info(f"[{self.plugin_name}] 插件服务已停止")
