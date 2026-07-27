# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import asyncio
import platform
import warnings

# ProactorEventLoop (IOCP) deadlocks when aiosqlite's background thread
# signals completion while asyncio is inside selectors._select on Windows CI
# runners — the async test hangs until pytest-timeout kills it.
# SelectorEventLoop avoids this; it is the same fix already applied in
# _new_sync_loop() for the benchmark variants in test_query_cache_perf.py.
#
# WindowsSelectorEventLoopPolicy and set_event_loop_policy are deprecated in
# Python 3.14 (removal in 3.16). Suppress the warnings until we migrate to a
# loop_factory approach in a future release.
if platform.system() == "Windows":
    warnings.filterwarnings("ignore", ".*WindowsSelectorEventLoopPolicy.*", DeprecationWarning)
    warnings.filterwarnings("ignore", ".*set_event_loop_policy.*", DeprecationWarning)
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
