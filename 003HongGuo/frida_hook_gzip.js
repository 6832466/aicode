// Frida script to hook GZIP compression and capture uncompressed request data
Java.perform(function() {
    console.log("[*] GZIP hook loaded");

    // 1. CertificatePinner bypass
    try {
        var CertificatePinner = Java.use("okhttp3.CertificatePinner");
        CertificatePinner.check.overload('java.lang.String', 'java.util.List').implementation = function(hostname, certs) {
            console.log("[+] CertPin bypassed: " + hostname);
        };
        CertificatePinner.check.overload('java.lang.String', '[Ljava.security.cert.Certificate;').implementation = function(hostname, certs) {
            console.log("[+] CertPin(array) bypassed: " + hostname);
        };
        console.log("[*] CertificatePinner hooked");
    } catch(e) {}

    // 2. Hook GZIPOutputStream to capture UNCOMPRESSED data before compression
    try {
        var GZIPOutputStream = Java.use("java.util.zip.GZIPOutputStream");
        var originalWrite = GZIPOutputStream.write.overload('[B', 'int', 'int');
        originalWrite.implementation = function(buf, off, len) {
            try {
                var str = Java.use("java.lang.String").$new(buf, off, len, "UTF-8");
                if (str.indexOf("video") >= 0 || str.indexOf("series") >= 0 ||
                    str.indexOf("player") >= 0 || str.indexOf("vod") >= 0) {
                    console.log("\n*** GZIP DATA (uncompressed) ***");
                    console.log(str);
                    console.log("*** END GZIP DATA ***\n");
                }
            } catch(e) {}
            return originalWrite.call(this, buf, off, len);
        };
        console.log("[*] GZIPOutputStream.write hooked");
    } catch(e) { console.log("[-] GZIPOutputStream: " + e); }

    // 3. Hook the RequestBody.create or writeTo for video requests
    try {
        // Hook okhttp3.RequestBody$Companion.create to capture body
        var RequestBody = Java.use("okhttp3.RequestBody");
        var createMethods = RequestBody.class.getDeclaredMethods();
        console.log("[*] RequestBody methods available");
    } catch(e) {}

    // 4. OkHttpClient hook for logging
    try {
        var OkHttpClient = Java.use("okhttp3.OkHttpClient");
        OkHttpClient.newCall.implementation = function(request) {
            var url = request.url().toString();
            var method = request.method();

            var isVideoApi = (url.indexOf("video_detail") >= 0 || url.indexOf("video_model") >= 0 ||
                              url.indexOf("vod/get") >= 0 || url.indexOf("play_info") >= 0 ||
                              url.indexOf("player/video") >= 0 || url.indexOf("player/multi_video") >= 0);

            if (isVideoApi) {
                console.log("\n*** VIDEO API CALL ***");
                console.log("[REQ] " + method + " " + url);
                var headers = request.headers();
                for (var i = 0; i < headers.size(); i++) {
                    console.log("  " + headers.name(i) + ": " + headers.value(i));
                }
            }

            return this.newCall(request);
        };
        console.log("[*] OkHttpClient hooked");
    } catch(e) {}

    // 5. Hook the response for video APIs
    try {
        var RealCall = Java.use("okhttp3.RealCall");
        var getResponseMethod = RealCall.getResponseWithInterceptorChain;
        getResponseMethod.implementation = function() {
            var response = getResponseMethod.call(this);
            var request = this.request();
            var url = request.url().toString();

            var isVideoApi = (url.indexOf("video_detail") >= 0 || url.indexOf("video_model") >= 0 ||
                              url.indexOf("vod/get") >= 0 || url.indexOf("play_info") >= 0 ||
                              url.indexOf("player/video") >= 0 || url.indexOf("player/multi_video") >= 0);

            if (isVideoApi) {
                console.log("\n*** VIDEO API RESPONSE ***");
                console.log("[RESP] " + url);
                console.log("  Status: " + response.code());
                try {
                    // Read response body via source
                    var body = response.body();
                    if (body != null) {
                        var source = body.source();
                        if (source != null) {
                            var Buffer = Java.use("okio.Buffer");
                            var buffer = Buffer.$new();
                            buffer.writeAll(source);
                            var bytes = buffer.readByteArray();
                            // Check gzip magic bytes: 0x1f 0x8b
                            if (bytes.length >= 2 && (bytes[0] & 0xFF) === 0x1f && (bytes[1] & 0xFF) === 0x8b) {
                                // Decompress
                                try {
                                    var GZIPInputStream = Java.use("java.util.zip.GZIPInputStream");
                                    var ByteArrayInputStream = Java.use("java.io.ByteArrayInputStream");
                                    var ByteArrayOutputStream = Java.use("java.io.ByteArrayOutputStream");
                                    var bais = ByteArrayInputStream.$new(bytes);
                                    var gzis = GZIPInputStream.$new(bais);
                                    var baos = ByteArrayOutputStream.$new();
                                    var buf = Java.array('byte', new Array(1024));
                                    var len;
                                    while ((len = gzis.read(buf)) > 0) {
                                        baos.write(buf, 0, len);
                                    }
                                    gzis.close();
                                    var result = baos.toString("UTF-8");
                                    console.log("  RESPONSE (decompressed): " + result);
                                    baos.close();
                                } catch(e) {
                                    console.log("  RESPONSE: [decompress error: " + e + "]");
                                }
                            } else {
                                console.log("  RESPONSE (raw): " + buffer.readUtf8());
                            }
                        }
                    }
                } catch(e) {
                    console.log("  RESPONSE: [error: " + e + "]");
                }
                console.log("*** END RESPONSE ***\n");
            }

            return response;
        };
        console.log("[*] RealCall.getResponseWithInterceptorChain hooked");
    } catch(e) { console.log("[-] Response hook: " + e); }

    // 6. Hook the network write to capture uncompressed request data
    // Hook the okio Buffer.write or similar
    try {
        var GzipSource = Java.use("okio.GzipSource");
        console.log("[*] GzipSource available");
    } catch(e) {}

    console.log("[*] GZIP hook init complete");
});
