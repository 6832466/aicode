// Frida: SSL bypass + ALL HTTP capture (req+resp) + auto-trigger playback
Java.perform(function() {
    console.log("[*] Capture script loaded");

    // ========== 1. CertificatePinner bypass ==========
    try {
        var CertificatePinner = Java.use("okhttp3.CertificatePinner");
        CertificatePinner.check.overload('java.lang.String', 'java.util.List').implementation = function(hostname, certs) {};
        CertificatePinner.check.overload('java.lang.String', '[Ljava.security.cert.Certificate;').implementation = function(hostname, certs) {};
        console.log("[*] CertificatePinner hooked");
    } catch(e) {}

    // ========== 2. Gzip helpers ==========
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

    function isGzip(bytes) {
        return bytes.length >= 2 && (bytes[0] & 0xFF) === 0x1f && (bytes[1] & 0xFF) === 0x8b;
    }

    function isVideoApi(url) {
        return (url.indexOf("multi_video_model") >= 0 ||
                url.indexOf("multi_video_detail") >= 0 ||
                url.indexOf("fqnovel.com/novel/player") >= 0);
    }

    // ========== 3. RealCall.execute hook to capture responses ==========
    try {
        var RealCall = Java.use("okhttp3.RealCall");
        RealCall.execute.implementation = function() {
            var request = this.request();
            var url = request.url().toString();

            if (isVideoApi(url)) {
                console.log("\n========== VIDEO API ==========");
                console.log("[REQ] " + request.method() + " " + url);

                // Log headers
                var headers = request.headers();
                for (var i = 0; i < headers.size(); i++) {
                    console.log("  REQ-HDR " + headers.name(i) + ": " + headers.value(i));
                }

                // Log body
                var body = request.body();
                if (body != null) {
                    try {
                        var Buffer = Java.use("okio.Buffer");
                        var buffer = Buffer.$new();
                        body.writeTo(buffer);
                        var rawBytes = buffer.readByteArray();
                        if (isGzip(rawBytes)) {
                            console.log("  REQ-BODY(gzip " + rawBytes.length + "): " + decompressGzip(rawBytes));
                        } else {
                            console.log("  REQ-BODY: " + buffer.readUtf8());
                        }
                    } catch(e) { console.log("  REQ-BODY: [error: " + e + "]"); }
                }
            }

            // Execute the actual call
            var response = this.execute();

            if (isVideoApi(url)) {
                console.log("[RESP] code=" + response.code());
                console.log("[RESP] " + response.message());

                // Log response headers
                try {
                    var respHeaders = response.headers();
                    for (var i = 0; i < respHeaders.size(); i++) {
                        console.log("  RESP-HDR " + respHeaders.name(i) + ": " + respHeaders.value(i));
                    }
                } catch(e) {}

                // Log response body
                try {
                    var source = response.body().source();
                    var Buffer = Java.use("okio.Buffer");
                    var respBuffer = Buffer.$new();
                    source.readAll(respBuffer);
                    var respBytes = respBuffer.readByteArray();
                    if (isGzip(respBytes)) {
                        var decompressed = decompressGzip(respBytes);
                        console.log("  RESP-BODY(gzip " + respBytes.length + "): " + decompressed);
                    } else {
                        console.log("  RESP-BODY(" + respBytes.length + "): " + respBuffer.clone().readUtf8());
                    }
                } catch(e) {
                    console.log("  RESP-BODY: [error: " + e + "]");
                }
                console.log("========== END ==========\n");
            }

            return response;
        };
        console.log("[*] RealCall.execute hooked for response capture");
    } catch(e) {
        console.log("[-] RealCall hook failed: " + e);
    }

    // ========== 4. Log ALL HTTP requests (lite) ==========
    try {
        var OkHttpClient = Java.use("okhttp3.OkHttpClient");
        OkHttpClient.newCall.implementation = function(request) {
            var url = request.url().toString();
            if (!isVideoApi(url)) {
                // Only log non-video API (video API is fully logged above)
                // console.log("[HTTP] " + request.method() + " " + url);
            }
            return this.newCall(request);
        };
        console.log("[*] OkHttpClient.newCall hooked");
    } catch(e) {}

    // ========== 5. Auto-trigger: find and click video ==========
    try {
        var Activity = Java.use("android.app.Activity");
        var didTrigger = false;

        Activity.onResume.implementation = function() {
            var className = this.getClass().getName();
            this.onResume();

            if (className.indexOf("ShortSeriesActivity") >= 0 && !didTrigger) {
                didTrigger = true;
                console.log("[*] ShortSeriesActivity detected!");

                Java.scheduleOnMainThread(function() {
                    Java.scheduleOnMainThread(function() {
                        tryTriggerPlayback();
                    });
                });
            }
        };
        console.log("[*] Activity.onResume hooked");
    } catch(e) {
        console.log("[-] onResume hook failed: " + e);
    }

    var triggerRetries = 0;

    function tryTriggerPlayback() {
        if (triggerRetries >= 6) {
            console.log("[-] Trigger retries exhausted");
            return;
        }
        triggerRetries++;
        console.log("[*] Trigger attempt " + triggerRetries);

        Java.choose("com.dragon.read.component.shortvideo.impl.ShortSeriesActivity", {
            onMatch: function(instance) {
                var decorView = instance.getWindow().getDecorView();
                var View = Java.use("android.view.View");
                var ViewPager = Java.use("androidx.viewpager.widget.ViewPager");

                // Use hardcoded ID from view tree dump: 0x7f1112ce
                var viewPager = decorView.findViewById(0x7f1112ce);
                console.log("[*] ViewPager (0x7f1112ce): " + (viewPager != null));

                if (viewPager != null) {
                    var vp = Java.cast(viewPager, ViewPager);
                    console.log("[*] Page: " + vp.getCurrentItem() + "/" + vp.getAdapter().getCount());

                    // Click ALL clickable views
                    console.log("[*] Clicking all views...");
                    clickAllViews(decorView, 0);

                    // Also try switching page
                    if (vp.getCurrentItem() === 0) {
                        vp.setCurrentItem(1, false);
                        console.log("[+] Switched to page 1");
                    }
                } else {
                    // Try alternate approach: dump what's visible
                    console.log("[*] ViewPager not ready, will retry...");
                    Java.scheduleOnMainThread(function() {
                        tryTriggerPlayback();
                    });
                }
            },
            onComplete: function() {
                console.log("[*] Attempt " + triggerRetries + " complete");
            }
        });
    }

    function clickAllViews(view, depth) {
        if (view == null || depth > 6) return;
        try {
            var View = Java.use("android.view.View");
            var v = Java.cast(view, View);
            if (v.isClickable()) {
                console.log("[*] CLICK: " + v.getClass().getName());
                v.performClick();
            }
            try {
                var ViewGroup = Java.use("android.view.ViewGroup");
                var vg = Java.cast(view, ViewGroup);
                for (var i = 0; i < vg.getChildCount(); i++) {
                    clickAllViews(vg.getChildAt(i), depth + 1);
                }
            } catch(e) {}
        } catch(e) {}
    }

    console.log("[*] Capture init complete");
});
