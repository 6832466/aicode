// Safe Frida SSL bypass + body capture for video API
Java.perform(function() {
    console.log("[*] Safe capture loaded");

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
    } catch(e) { console.log("[-] CertPin: " + e); }

    // 2. OkHttpClient.newCall - capture all requests (URL + headers + body)
    try {
        var OkHttpClient = Java.use("okhttp3.OkHttpClient");
        OkHttpClient.newCall.implementation = function(request) {
            var url = request.url().toString();
            var method = request.method();

            console.log("[OKHTTP] " + method + " " + url);

            // Print headers
            var headers = request.headers();
            for (var i = 0; i < headers.size(); i++) {
                console.log("  " + headers.name(i) + ": " + headers.value(i));
            }

            // Try to read body for POST requests
            if (method === "POST") {
                var body = request.body();
                if (body != null) {
                    try {
                        var Buffer = Java.use("okio.Buffer");
                        var buffer = Buffer.$new();
                        body.writeTo(buffer);
                        var bodyStr = buffer.readUtf8();
                        if (bodyStr.length < 5000) {
                            console.log("  BODY: " + bodyStr);
                        } else {
                            console.log("  BODY(truncated): " + bodyStr.substring(0, 2000) + "...");
                        }
                    } catch(e) {
                        console.log("  BODY: [error: " + e + "]");
                    }
                }
            }

            return this.newCall(request);
        };
        console.log("[*] OkHttpClient hooked");
    } catch(e) { console.log("[-] OkHttpClient: " + e); }

    // 3. Hook RealInterceptorChain to capture response bodies (safer than RealCall)
    try {
        var RealInterceptorChain = Java.use("okhttp3.internal.http.RealInterceptorChain");
        RealInterceptorChain.proceed.implementation = function(request) {
            var response = this.proceed(request);
            var reqUrl = request.url().toString();

            if (reqUrl.indexOf("video_detail") >= 0 || reqUrl.indexOf("video_model") >= 0 ||
                reqUrl.indexOf("vod/get") >= 0 || reqUrl.indexOf("play_info") >= 0 ||
                reqUrl.indexOf("snssdk.com/vod") >= 0 || reqUrl.indexOf("player") >= 0) {

                console.log("\n*** VIDEO API RESPONSE ***");
                console.log("URL: " + reqUrl);
                console.log("Status: " + response.code());

                try {
                    var body = response.body();
                    if (body != null) {
                        var source = body.source();
                        if (source != null) {
                            var Buffer = Java.use("okio.Buffer");
                            var buffer = Buffer.$new();
                            buffer.writeAll(source);
                            var bodyStr = buffer.readUtf8();
                            console.log("RESPONSE BODY: " + bodyStr);
                        }
                    }
                } catch(e) {
                    console.log("RESPONSE BODY error: " + e);
                }
                console.log("*** END VIDEO API ***\n");
            }

            return response;
        };
        console.log("[*] RealInterceptorChain hooked");
    } catch(e) { console.log("[-] InterceptorChain: " + e); }

    console.log("[*] Safe capture init complete");
});
