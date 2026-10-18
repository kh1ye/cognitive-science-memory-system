export async function api(path, options = {}) {
  const { timeoutMs = 20000, ...fetchOptions } = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(path, {
      ...fetchOptions,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...options.headers },
    });
    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error("服务返回异常，请检查服务状态。");
    }
    if (!response.ok)
      throw new Error(data.message || data.detail || "请求失败，请稍后重试。");
    return data;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("请求超时，请稍后重试。");
    throw error;
  } finally {
    clearTimeout(timer);
  }
}
export const post = (path, body, options = {}) =>
  api(path, { ...options, method: "POST", body: JSON.stringify(body) });
