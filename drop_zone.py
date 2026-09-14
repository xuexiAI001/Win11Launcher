# -*- coding: utf-8 -*-
"""
拖放接收区域组件 - 显示拖拽提示，接收文件拖放
"""
import customtkinter as ctk


class DropZone(ctk.CTkFrame):
    """拖放接收区域"""

    def __init__(self, parent, drop_callback):
        super().__init__(
            parent,
            fg_color=("#EFEFEF", "#1A1A1A"),
            corner_radius=8,
            border_width=2,
            border_color=("#0078D4", "#0078D4")
        )
        self.drop_callback = drop_callback

        self.pack_propagate(False)

        self.label = ctk.CTkLabel(
            self,
            text="拖拽文件到这里添加应用",
            font=ctk.CTkFont(size=14),
            text_color=("#666666", "#666666")
        )
        self.label.pack(expand=True)
