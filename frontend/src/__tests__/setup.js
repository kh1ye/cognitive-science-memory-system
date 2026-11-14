import { beforeEach } from "vitest";
import { config } from "@vue/test-utils";
import { setLanguage, t } from "../lib/i18n";

config.global.mocks = { ...config.global.mocks, $t: t };
beforeEach(() => setLanguage("zh"));
