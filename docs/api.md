# 东方财富概念板块个股现金流接口样本

- 页面：`https://data.eastmoney.com/bkzj/BK1713.html`
  
## 首页
接口：https://push2.eastmoney.com/api/qt/clist/get?cb=jQuery112308919976767496475_1784950159345&fid=f62&po=1&pz=50&pn=1&np=1&fltt=2&invt=2&ut=8dec03ba335b81bf4ebdf7b29ec27d15&fs=b%3ABK1713&fields=f12%2Cf14%2Cf2%2Cf3%2Cf62%2Cf184%2Cf66%2Cf69%2Cf72%2Cf75%2Cf78%2Cf81%2Cf84%2Cf87%2Cf204%2Cf205%2Cf124%2Cf1%2Cf13

请求：
GET /api/qt/clist/get?cb=jQuery112308919976767496475_1784950159345&fid=f62&po=1&pz=50&pn=1&np=1&fltt=2&invt=2&ut=8dec03ba335b81bf4ebdf7b29ec27d15&fs=b%3ABK1713&fields=f12%2Cf14%2Cf2%2Cf3%2Cf62%2Cf184%2Cf66%2Cf69%2Cf72%2Cf75%2Cf78%2Cf81%2Cf84%2Cf87%2Cf204%2Cf205%2Cf124%2Cf1%2Cf13 HTTP/1.1
Accept: */*
Accept-Encoding: gzip, deflate, br, zstd
Accept-Language: zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7
Connection: keep-alive
Cookie: qgqp_b_id=af4fde27e8e3741484e1e06c89b18cd8; st_nvi=Dv7IPWsQi2JVCW9rdCgLS9702; mtp=1; sid=; nid18=020e9a775620cbf9a1710f09abd84bab; nid18_create_time=1784801307408; gviem=Dz5M1ed-2JlkpTXEcOUwJcaab; gviem_create_time=1784801307408; vtpst=%7c; st_si=42159540565953; fullscreengg=1; fullscreengg2=1; st_asi=delete; st_pvi=64573443183295; st_sp=2026-04-15%2009%3A50%3A47; st_inirUrl=https%3A%2F%2Fpassport2.eastmoney.com%2F; st_sn=29; st_psi=20260725112913314-113300300992-3450809537
Host: push2.eastmoney.com
Referer: https://data.eastmoney.com/bkzj/BK1713.html
Sec-Fetch-Dest: script
Sec-Fetch-Mode: no-cors
Sec-Fetch-Site: same-site
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36
sec-ch-ua: "Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"
sec-ch-ua-mobile: ?0
sec-ch-ua-platform: "Windows"

响应：
jQuery112308919976767496475_1784950159345({
    "rc": 0,
    "rt": 6,
    "svr": 181669473,
    "lt": 1,
    "full": 1,
    "dlmkts": "",
    "dsc": "0",
    "data": {
        "total": 100,
        "diff": [{
            "f1": 2,
            "f2": 76.64,
            "f3": 9.77,
            "f12": "002156",
            "f13": 0,
            "f14": "通富微电",
            "f62": 2471768784.0,
            "f66": 3312779776.0,
            "f69": 16.72,
            "f72": -841010992.0,
            "f75": -4.24,
            "f78": -1320832352.0,
            "f81": -6.66,
            "f84": -1150936576.0,
            "f87": -5.81,
            "f124": 1784878479,
            "f184": 12.47,
            "f204": "-",
            "f205": "-",
            "f206": "-"
        }]
    }
}

## 第二页：
接口：https://push2.eastmoney.com/api/qt/clist/get?cb=jQuery112308919976767496475_1784950159345&fid=f62&po=1&pz=50&pn=2&np=1&fltt=2&invt=2&ut=8dec03ba335b81bf4ebdf7b29ec27d15&fs=b%3ABK1713&fields=f12%2Cf14%2Cf2%2Cf3%2Cf62%2Cf184%2Cf66%2Cf69%2Cf72%2Cf75%2Cf78%2Cf81%2Cf84%2Cf87%2Cf204%2Cf205%2Cf124%2Cf1%2Cf13

请求：
GET /api/qt/clist/get?cb=jQuery112308919976767496475_1784950159345&fid=f62&po=1&pz=50&pn=2&np=1&fltt=2&invt=2&ut=8dec03ba335b81bf4ebdf7b29ec27d15&fs=b%3ABK1713&fields=f12%2Cf14%2Cf2%2Cf3%2Cf62%2Cf184%2Cf66%2Cf69%2Cf72%2Cf75%2Cf78%2Cf81%2Cf84%2Cf87%2Cf204%2Cf205%2Cf124%2Cf1%2Cf13 HTTP/1.1
Accept: */*
Accept-Encoding: gzip, deflate, br, zstd
Accept-Language: zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7
Connection: keep-alive
Cookie: qgqp_b_id=af4fde27e8e3741484e1e06c89b18cd8; st_nvi=Dv7IPWsQi2JVCW9rdCgLS9702; mtp=1; sid=; nid18=020e9a775620cbf9a1710f09abd84bab; nid18_create_time=1784801307408; gviem=Dz5M1ed-2JlkpTXEcOUwJcaab; gviem_create_time=1784801307408; vtpst=%7c; st_si=42159540565953; fullscreengg=1; fullscreengg2=1; st_asi=delete; st_pvi=64573443183295; st_sp=2026-04-15%2009%3A50%3A47; st_inirUrl=https%3A%2F%2Fpassport2.eastmoney.com%2F; st_sn=30; st_psi=20260725112919409-113300300992-3566716838
Host: push2.eastmoney.com
Referer: https://data.eastmoney.com/bkzj/BK1713.html
Sec-Fetch-Dest: script
Sec-Fetch-Mode: no-cors
Sec-Fetch-Site: same-site
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36
sec-ch-ua: "Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"
sec-ch-ua-mobile: ?0
sec-ch-ua-platform: "Windows"

响应：

jQuery112308919976767496475_1784950159345({
    "rc": 0,
    "rt": 6,
    "svr": 177617655,
    "lt": 1,
    "full": 1,
    "dlmkts": "",
    "dsc": "0",
    "data": {
        "total": 100,
        "diff": [{
            "f1": 2,
            "f2": 56.33,
            "f3": -1.04,
            "f12": "688172",
            "f13": 1,
            "f14": "燕东微",
            "f62": -51284803.0,
            "f66": 51459.0,
            "f69": 0.01,
            "f72": -51336262.0,
            "f75": -5.49,
            "f78": 16834416.0,
            "f81": 1.8,
            "f84": 34450400.0,
            "f87": 3.69,
            "f124": 1784880713,
            "f184": -5.49,
            "f204": "-",
            "f205": "-",
            "f206": "-"
        }]
    }
}
    