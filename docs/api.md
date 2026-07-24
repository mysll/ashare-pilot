# 东方财富概念板块列表接口样本

- 日期：2026-07-23
- 页面：`https://data.eastmoney.com/bkzj/gn.html`
- 安全：Cookie 只从工作区 `.cookie` 读取，本文不保存凭据

概念版块第一页,默认每页50，url:https://data.eastmoney.com/bkzj/gn.html：
GET /weblogin/api/qt/clist/get?np=1&fltt=1&invt=2&cb=jQuery37107928327313745926_1784858770219&fs=m%3A90%2Bt%3A3%2Bf%3A!50&fields=f12%2Cf13%2Cf14%2Cf1%2Cf2%2Cf4%2Cf3%2Cf152%2Cf20%2Cf8%2Cf104%2Cf105%2Cf128%2Cf140%2Cf141%2Cf207%2Cf208%2Cf209%2Cf136%2Cf222&fid=f3&pn=1&pz=20&po=1&dect=1&ut=fa5fd1943c7b386f172d6893dbfba10b&wbp2u=5869087587072820%7C0%7C1%7C0%7Cweb&_=1784858770225 HTTP/1.1
Accept: */*
Accept-Encoding: gzip, deflate, br, zstd
Accept-Language: zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7
Connection: keep-alive
Cookie: qgqp_b_id=af4fde27e8e3741484e1e06c89b18cd8; st_nvi=Dv7IPWsQi2JVCW9rdCgLS9702; mtp=1; sid=; vtpst=|; ct=dUKJaBYf08yAYhs83M3N49x0QzpNi0BNUDwpfQUJZJeABQcFCKFiIDwsTII8xwlID4ZcFnI0qZc9NIZiXL2dhMW2M0tqF2DBX-p2qkEvqpx8XZmnsvQd2Rm2xpdixk4FtyBAJ_ybTv5gAJIEbRmGRZxhm7JT2To8XXwSq3L2dK0; ut=FobyicMgeV7bodPh3F8eYjtLNIxqzZflmQelDRXb22VuDEBUbyT1JT-AFBNEkAApqrUMIdooYVN-TIf6VZtNiiYcP0x-aTJZ52NDF_iQ3tGeodCXoBYM_vUNl3-ybxncWqcpPHod2zZJcvYaOP2K9mEGfK_ItVKRNKRyXZD9zV2mO6JLNy7WPRsGLXKJydr8bv_CrbeiLz8j_gsEy9a5KHbLDEukloKCioPHFlCFIjSH9PKKu1DcFcsl1is_t7c6gSWgOEUi46jf8O-lQQFn3EpXMjWRSZ-n; pi=5869087587072820%3Bc5869087587072820%3B%E8%82%A1%E5%8F%8Bz100282Q66%3Buqmd2%2Fx%2FzrehmhAZUjXLXLj4%2Fzcv2tk64Cpr3e45RKpXujOnBgq%2FYyPbT9u4ErE59yAuWqmiHjJfexRfiVJNMm0XzC9NPP%2FdtGEbYC1RMS6UHYo%2FGa%2FCzKKBPe2OPJasLfw8jgN5B3o%2BXutgTJjA8BunMBax%2B96PozU2qlr2Gz6C5AbbmYgj5eSrbMxt8K8wL31VwyHx%3BHp25SnszraaLb43hn8rVaITcBQHwaY1dqmuS2vDHj5hxSRw%2BUaq0ZVF024r2F1JwD3kFxPv7sp2wKAh6FnMOITgMh%2FJglWIDuE3Cw%2FDdogbrH9KKz8XFuM46wmNNOQVM44HoMiysN7Ehv7WT8LPKEDZ1u7j0eQ%3D%3D; uidal=5869087587072820%e8%82%a1%e5%8f%8bz100282Q66; st_si=87858862796506; nid18=020e9a775620cbf9a1710f09abd84bab; nid18_create_time=1784801307408; gviem=Dz5M1ed-2JlkpTXEcOUwJcaab; gviem_create_time=1784801307408; fullscreengg=1; fullscreengg2=1; st_asi=delete; wsc_checkuser_ok=1; st_pvi=64573443183295; st_sp=2026-04-15%2009%3A50%3A47; st_inirUrl=https%3A%2F%2Fpassport2.eastmoney.com%2F; st_sn=27; st_psi=20260724100336181-113200313002-4451204202
Host: push2.eastmoney.com
Referer: https://quote.eastmoney.com/center/gridlist.html
Sec-Fetch-Dest: script
Sec-Fetch-Mode: no-cors
Sec-Fetch-Site: same-site
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36
sec-ch-ua: "Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"
sec-ch-ua-mobile: ?0
sec-ch-ua-platform: "Windows"

响应：
jQuery37107928327313745926_1784858770219({
    "rc": 0,
    "rt": 6,
    "svr": 175640632,
    "lt": 1,
    "full": 1,
    "dlmkts": "",
    "dsc": "0",
    "data": {
        "total": 495,
        "diff": [{
            "f1": 2,
            "f2": 3327451,
            "f3": 305,
            "f4": 98401,
            "f8": 973,
            "f12": "BK1051",
            "f13": 90,
            "f14": "昨日连板_含一字",
            "f20": 121010398000,
            "f104": 9,
            "f105": 6,
            "f128": "五洲医疗",
            "f140": "301234",
            "f141": 0,
            "f136": 2000,
            "f152": 2,
            "f207": "证通电子",
            "f208": "002197",
            "f209": 0,
            "f222": -795
        }]
    }
});

第二页：
GET /weblogin/api/qt/clist/get?np=1&fltt=1&invt=2&cb=jQuery37107928327313745926_1784858770223&fs=m%3A90%2Bt%3A3%2Bf%3A!50&fields=f12%2Cf13%2Cf14%2Cf1%2Cf2%2Cf4%2Cf3%2Cf152%2Cf20%2Cf8%2Cf104%2Cf105%2Cf128%2Cf140%2Cf141%2Cf207%2Cf208%2Cf209%2Cf136%2Cf222&fid=f3&pn=2&pz=20&po=1&dect=1&ut=fa5fd1943c7b386f172d6893dbfba10b&wbp2u=5869087587072820%7C0%7C1%7C0%7Cweb&_=1784858770230 HTTP/1.1
Accept: */*
Accept-Encoding: gzip, deflate, br, zstd
Accept-Language: zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7
Connection: keep-alive
Cookie: qgqp_b_id=af4fde27e8e3741484e1e06c89b18cd8; st_nvi=Dv7IPWsQi2JVCW9rdCgLS9702; mtp=1; sid=; vtpst=|; ct=dUKJaBYf08yAYhs83M3N49x0QzpNi0BNUDwpfQUJZJeABQcFCKFiIDwsTII8xwlID4ZcFnI0qZc9NIZiXL2dhMW2M0tqF2DBX-p2qkEvqpx8XZmnsvQd2Rm2xpdixk4FtyBAJ_ybTv5gAJIEbRmGRZxhm7JT2To8XXwSq3L2dK0; ut=FobyicMgeV7bodPh3F8eYjtLNIxqzZflmQelDRXb22VuDEBUbyT1JT-AFBNEkAApqrUMIdooYVN-TIf6VZtNiiYcP0x-aTJZ52NDF_iQ3tGeodCXoBYM_vUNl3-ybxncWqcpPHod2zZJcvYaOP2K9mEGfK_ItVKRNKRyXZD9zV2mO6JLNy7WPRsGLXKJydr8bv_CrbeiLz8j_gsEy9a5KHbLDEukloKCioPHFlCFIjSH9PKKu1DcFcsl1is_t7c6gSWgOEUi46jf8O-lQQFn3EpXMjWRSZ-n; pi=5869087587072820%3Bc5869087587072820%3B%E8%82%A1%E5%8F%8Bz100282Q66%3Buqmd2%2Fx%2FzrehmhAZUjXLXLj4%2Fzcv2tk64Cpr3e45RKpXujOnBgq%2FYyPbT9u4ErE59yAuWqmiHjJfexRfiVJNMm0XzC9NPP%2FdtGEbYC1RMS6UHYo%2FGa%2FCzKKBPe2OPJasLfw8jgN5B3o%2BXutgTJjA8BunMBax%2B96PozU2qlr2Gz6C5AbbmYgj5eSrbMxt8K8wL31VwyHx%3BHp25SnszraaLb43hn8rVaITcBQHwaY1dqmuS2vDHj5hxSRw%2BUaq0ZVF024r2F1JwD3kFxPv7sp2wKAh6FnMOITgMh%2FJglWIDuE3Cw%2FDdogbrH9KKz8XFuM46wmNNOQVM44HoMiysN7Ehv7WT8LPKEDZ1u7j0eQ%3D%3D; uidal=5869087587072820%e8%82%a1%e5%8f%8bz100282Q66; st_si=87858862796506; nid18=020e9a775620cbf9a1710f09abd84bab; nid18_create_time=1784801307408; gviem=Dz5M1ed-2JlkpTXEcOUwJcaab; gviem_create_time=1784801307408; fullscreengg=1; fullscreengg2=1; st_asi=delete; wsc_checkuser_ok=1; st_pvi=64573443183295; st_sp=2026-04-15%2009%3A50%3A47; st_inirUrl=https%3A%2F%2Fpassport2.eastmoney.com%2F; st_sn=28; st_psi=20260724100610588-113200313002-5577414106
Host: push2.eastmoney.com
Referer: https://quote.eastmoney.com/center/gridlist.html
Sec-Fetch-Dest: script
Sec-Fetch-Mode: no-cors
Sec-Fetch-Site: same-site
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36
sec-ch-ua: "Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"
sec-ch-ua-mobile: ?0
sec-ch-ua-platform: "Windows"

响应：
jQuery37107928327313745926_1784858770223({
    "rc": 0,
    "rt": 6,
    "svr": 181735022,
    "lt": 1,
    "full": 1,
    "dlmkts": "",
    "dsc": "0",
    "data": {
        "total": 495,
        "diff": [{
            "f1": 2,
            "f2": 201475,
            "f3": 57,
            "f4": 1145,
            "f8": 139,
            "f12": "BK0977",
            "f13": 90,
            "f14": "碳化硅",
            "f20": 1397724960000,
            "f104": 19,
            "f105": 28,
            "f128": "光力科技",
            "f140": "300480",
            "f141": 0,
            "f136": 2002,
            "f152": 2,
            "f207": "奥瑞德",
            "f208": "600666",
            "f209": 1,
            "f222": -353
        }]
    }
}


版块股票:
