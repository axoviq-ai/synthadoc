// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Peter White / axoviq.com
import remarkGfm from "remark-gfm";
import remarkCjkFriendly from "remark-cjk-friendly";

// The remark plugins every <ReactMarkdown> in the app uses.
//
// remark-cjk-friendly fixes CommonMark's emphasis rule for Chinese, Japanese and
// Korean text: "**" may only open/close next to punctuation when whitespace or
// punctuation is on the other side, which CJK text rarely has, so
//     **重点（强调）**后续文字     or     文字**（加粗）**文字
// was shown with literal asterisks. Ordinary (English) markdown is unaffected.
export const markdownPlugins = [remarkGfm, remarkCjkFriendly];
