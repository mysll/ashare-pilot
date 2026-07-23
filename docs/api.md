# 东方财富概念板块列表接口样本

- 日期：2026-07-23
- 页面：`https://data.eastmoney.com/bkzj/gn.html`
- 安全：Cookie 只从工作区 `.cookie` 读取，本文不保存凭据

接口一 `dataapi/bkzj/getbkzj` 一次返回全部代码和名称，用于校验 total
及代码/名称全集。它的字段不足以单独替换完整的 `concepts.json`。

GET /dataapi/bkzj/getbkzj?key=f62&code=m%3A90%2Bt%3A3 HTTP/1.1
Accept: */*
Accept-Encoding: gzip, deflate, br, zstd
Accept-Language: zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7
Connection: keep-alive
Cookie: <redacted; loaded from .cookie>
Host: data.eastmoney.com
Referer: https://data.eastmoney.com/bkzj/gn.html
Sec-Fetch-Dest: empty
Sec-Fetch-Mode: cors
Sec-Fetch-Site: same-origin
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36
X-Requested-With: XMLHttpRequest
sec-ch-ua: "Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"
sec-ch-ua-mobile: ?0
sec-ch-ua-platform: "Windows"

resp:
{
    "rc": 0,
    "rt": 6,
    "svr": 177617910,
    "lt": 1,
    "full": 1,
    "dlmkts": "",
    "dsc": "0",
    "data": {
        "total": 495,
        "diff": [
            {
                "f12": "BK1648",
                "f13": 90,
                "f14": "电池技术",
                "f62": 10951472128
            }]
    }
}


接口二 `push2/api/qt/clist/get` 按网页原生的每页 50 条返回完整行情详情，
用于保持现有 `concepts.json` 字段合同。

GET /api/qt/clist/get?cb=jQuery1123015924300167159444_1784806885737&fid=f62&po=1&pz=50&pn=1&np=1&fltt=2&invt=2&ut=8dec03ba335b81bf4ebdf7b29ec27d15&fs=m%3A90+t%3A3&fields=f12%2Cf14%2Cf2%2Cf3%2Cf62%2Cf184%2Cf66%2Cf69%2Cf72%2Cf75%2Cf78%2Cf81%2Cf84%2Cf87%2Cf204%2Cf205%2Cf124%2Cf1%2Cf13 HTTP/1.1
Accept: */*
Accept-Encoding: gzip, deflate, br, zstd
Accept-Language: zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7
Connection: keep-alive
Cookie: <redacted; loaded from .cookie>
Host: push2.eastmoney.com
Referer: https://data.eastmoney.com/bkzj/gn.html
Sec-Fetch-Dest: script
Sec-Fetch-Mode: no-cors
Sec-Fetch-Site: same-site
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36
sec-ch-ua: "Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"
sec-ch-ua-mobile: ?0
sec-ch-ua-platform: "Windows"

resp:
jQuery1123015924300167159444_1784806885737({
    "rc": 0,
    "rt": 6,
    "svr": 180606323,
    "lt": 1,
    "full": 1,
    "dlmkts": "",
    "dsc": "0",
    "data": {
        "total": 495,
        "diff": [{
            "f1": 2,
            "f2": 833.27,
            "f3": 2.87,
            "f12": "BK1648",
            "f13": 90,
            "f14": "电池技术",
            "f62": 10951472128.0,
            "f66": 6545331200.0,
            "f69": 1.95,
            "f72": 4406140928.0,
            "f75": 1.31,
            "f78": -4580184064.0,
            "f81": -1.37,
            "f84": -6311772160.0,
            "f87": -1.88,
            "f124": 1784792372,
            "f184": 3.26,
            "f204": "宁德时代",
            "f205": "300750",
            "f206": 0
        }}
})

## 生产合同与验证

- 固定 Windows Chrome 指纹并复用 HTTP Session。
- Referer 为 `https://data.eastmoney.com/bkzj/gn.html`。
- 分页合同使用 `fid=f62`、动态 JSONP 回调和网页当前 `ut`；`pz` 由
  `config/themes/theme-config.json` 的
  `fetch_settings.concept_board_page_size` 控制。
- 成分股接口的 `pz` 由同一配置中的
  `fetch_settings.concept_member_page_size` 控制。两个配置项的有效范围均为
  1–100，当前值均为 50。
- `concepts_fetch_state.json` 记录 schema 与请求合同；不兼容的旧 checkpoint
  自动从第一页重新获取。
- 任一分页失败只保存 checkpoint，不发布部分 `concepts.json`。
- 两个接口的 total、代码集合和名称必须一致。

2026-07-23 live 验证：接口一返回 495 个板块；接口二连续完成 10 页并获得
495 个唯一板块；代码和名称全集一致。
