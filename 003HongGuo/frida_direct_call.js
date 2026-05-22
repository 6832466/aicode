// Frida: Directly invoke the video API using app's OkHttpClient
Java.perform(function() {
    console.log("[*] Direct API call script loaded");

    // CertificatePinner bypass
    try {
        var CertificatePinner = Java.use("okhttp3.CertificatePinner");
        CertificatePinner.check.overload('java.lang.String', 'java.util.List').implementation = function(h, c) {};
        CertificatePinner.check.overload('java.lang.String', '[Ljava.security.cert.Certificate;').implementation = function(h, c) {};
        console.log("[*] CertPin bypassed");
    } catch(e) {}

    function isGzip(bytes) {
        return bytes.length >= 2 && (bytes[0] & 0xFF) === 0x1f && (bytes[1] & 0xFF) === 0x8b;
    }

    function decompressGzip(compressedBytes) {
        try {
            var GZIPInputStream = Java.use("java.util.zip.GZIPInputStream");
            var ByteArrayInputStream = Java.use("java.io.ByteArrayInputStream");
            var ByteArrayOutputStream = Java.use("java.io.ByteArrayOutputStream");
            var bais = ByteArrayInputStream.$new(compressedBytes);
            var gzis = GZIPInputStream.$new(bais);
            var baos = ByteArrayOutputStream.$new();
            var buf = Java.array('byte', new Array(4096));
            var len;
            while ((len = gzis.read(buf)) > 0) { baos.write(buf, 0, len); }
            gzis.close();
            var result = baos.toString("UTF-8");
            baos.close();
            return result;
        } catch(e) { return null; }
    }

    // ========== Hook RealCall.execute to capture video API full request/response ==========
    try {
        var RealCall = Java.use("okhttp3.RealCall");

        RealCall.execute.implementation = function() {
            var request = this.request();
            var url = request.url().toString();
            var isVideo = (url.indexOf("multi_video_model") >= 0 ||
                           url.indexOf("multi_video_detail") >= 0);

            if (isVideo) {
                console.log("\n========== [CAPTURE] VIDEO API ==========");
                console.log("[METHOD] " + request.method());
                console.log("[URL] " + url);

                // All headers
                var hdrs = request.headers();
                for (var i = 0; i < hdrs.size(); i++) {
                    console.log("[HDR] " + hdrs.name(i) + ": " + hdrs.value(i));
                }

                // Request body
                var body = request.body();
                if (body != null) {
                    try {
                        var Buffer = Java.use("okio.Buffer");
                        var buf = Buffer.$new();
                        body.writeTo(buf);
                        var raw = buf.readByteArray();
                        console.log("[REQ-BODY-RAW] " + raw.length + " bytes");
                        if (isGzip(raw)) {
                            console.log("[REQ-BODY] " + decompressGzip(raw));
                        } else {
                            console.log("[REQ-BODY] " + buf.clone().readUtf8());
                        }
                    } catch(e) { console.log("[REQ-BODY-ERR] " + e); }
                }
            }

            var response = this.execute();

            if (isVideo) {
                console.log("[RESP-CODE] " + response.code());

                // Response headers
                try {
                    var rhdrs = response.headers();
                    for (var i = 0; i < rhdrs.size(); i++) {
                        console.log("[RESP-HDR] " + rhdrs.name(i) + ": " + rhdrs.value(i));
                    }
                } catch(e) {}

                // Response body
                try {
                    var respBody = response.body();
                    var source = respBody.source();
                    var Buffer = Java.use("okio.Buffer");
                    var rb = Buffer.$new();
                    source.readAll(rb);
                    var rawResp = rb.readByteArray();
                    console.log("[RESP-BODY-RAW] " + rawResp.length + " bytes");
                    if (isGzip(rawResp)) {
                        console.log("[RESP-BODY] " + decompressGzip(rawResp));
                    } else {
                        console.log("[RESP-BODY] " + rb.clone().readUtf8());
                    }
                } catch(e) {
                    console.log("[RESP-BODY-ERR] " + e);
                }
                console.log("========== END CAPTURE ==========\n");
            }

            return response;
        };
        console.log("[*] RealCall.execute hooked");
    } catch(e) {
        console.log("[-] RealCall hook failed: " + e);
    }

    // ========== Hook OkHttpClient to capture instance ==========
    var globalClient = null;
    try {
        var OkHttpClient = Java.use("okhttp3.OkHttpClient");
        OkHttpClient.newCall.implementation = function(request) {
            if (globalClient == null) {
                globalClient = Java.retain(this);
                console.log("[*] Captured OkHttpClient instance");
            }
            return this.newCall(request);
        };
        console.log("[*] OkHttpClient hooked (will capture instance)");
    } catch(e) {}

    // ========== Direct API call function ==========
    function makeVideoApiCall(seriesId, videoId) {
        console.log("\n[*] Making direct video API call...");
        console.log("[*] series_id: " + seriesId);
        console.log("[*] vid: " + videoId);

        try {
            // Build URL with query params (from observed captures)
            var params = "iid=3805822112787207&device_id=3805822112783111&ac=wifi" +
                "&channel=hongguo_baidu_pz_kaiping0105_android&aid=8662" +
                "&app_name=novelread&version_code=65532&version_name=6.5.5.32" +
                "&device_platform=android&os=android&ssmix=a&device_type=BVL-AN16" +
                "&device_brand=HONOR&language=zh&os_api=32&os_version=12" +
                "&manifest_version_code=65532&resolution=1920*1080&dpi=280" +
                "&update_version_code=65532&pv_player=65532" +
                "&need_personal_recommend=1&player_so_load=1&is_android_pad_screen=1" +
                "&host_abi=arm64-v8a&dragon_device_type=phone" +
                "&rom_version=V417IR+release-keys&compliance_status=0" +
                "&cdid=31b09333-09a1-4d66-9ecf-235418a5492e&_rticket=" + Date.now();

            var url = "https://api5-normal-sinfonlinec.fqnovel.com/novel/player/multi_video_model/v1/?" + params;
            console.log("[URL] " + url);

            // Build JSON body (try common patterns)
            var bodyJson = JSON.stringify({
                "series_id": seriesId,
                "vid": videoId,
                "video_series_id": seriesId
            });
            console.log("[BODY-JSON] " + bodyJson);

            // Gzip compress the body
            var ByteArrayOutputStream = Java.use("java.io.ByteArrayOutputStream");
            var GZIPOutputStream = Java.use("java.util.zip.GZIPOutputStream");
            var baos = ByteArrayOutputStream.$new();
            var gzos = GZIPOutputStream.$new(baos);
            var bodyBytes = Java.array('byte', bodyJson.split('').map(function(c) { return c.charCodeAt(0); }));
            gzos.write(bodyBytes, 0, bodyBytes.length);
            gzos.close();
            var compressed = baos.toByteArray();
            console.log("[BODY-GZIP] " + compressed.length + " bytes");

            // Create Request
            var Request = Java.use("okhttp3.Request");
            var RequestBody = Java.use("okhttp3.RequestBody");
            var MediaType = Java.use("okhttp3.MediaType");

            var mediaType = MediaType.parse("application/json; charset=utf-8");
            var requestBody = RequestBody.create(mediaType, compressed);

            var request = Request.Builder().$new()
                .url(url)
                .method("POST", requestBody)
                .header("Content-Encoding", "gzip")
                .header("Accept", "application/json; charset=utf-8,application/x-protobuf")
                .header("X-Xs-From-Web", "0")
                .build();

            // Create OkHttpClient directly (public constructor)
            var OkHttpClient = Java.use("okhttp3.OkHttpClient");
            var client = OkHttpClient.$new();
            console.log("[*] Created OkHttpClient: " + client);

            // Execute the call
            console.log("[*] Executing...");
            var realCall = client.newCall(request);
            var response = realCall.execute();
            console.log("[RESP] " + response.code() + " " + response.message());

            // Read response
            var respSource = response.body().source();
            var Buffer = Java.use("okio.Buffer");
            var respBuf = Buffer.$new();
            respSource.readAll(respBuf);
            var respBytes = respBuf.readByteArray();
            if (isGzip(respBytes)) {
                console.log("[RESP-BODY] " + decompressGzip(respBytes));
            } else {
                console.log("[RESP-BODY] " + respBuf.clone().readUtf8());
            }

            console.log("[+] Direct API call complete!");
        } catch(e) {
            console.log("[-] Direct API call error: " + e);
        }
    }

    // ========== Auto-trigger on ShortSeriesActivity + make API call ==========
    try {
        var Activity = Java.use("android.app.Activity");
        var didTrigger = false;

        Activity.onResume.implementation = function() {
            var className = this.getClass().getName();
            this.onResume();

            if (className.indexOf("ShortSeriesActivity") >= 0 && !didTrigger) {
                didTrigger = true;
                console.log("[*] ShortSeriesActivity detected!");

                // After UI settles, make direct API call
                Java.scheduleOnMainThread(function() {
                    Java.scheduleOnMainThread(function() {
                        makeVideoApiCall("7482259558660852798", "7482697749591231512");
                    });
                });
            }
        };
        console.log("[*] Activity.onResume hooked");
    } catch(e) {}

    console.log("[*] Direct call script ready");
});
