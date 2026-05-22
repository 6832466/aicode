// Frida: SSL bypass + gzip capture + auto-trigger first episode (Activity.onCreate version)
Java.perform(function() {
    console.log("[*] AutoPlay script loaded");

    // ========== 1. CertificatePinner bypass ==========
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

    // ========== 2. Gzip decompress helper ==========
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

    // ========== 3. OkHttpClient.newCall capture ==========
    try {
        var OkHttpClient = Java.use("okhttp3.OkHttpClient");
        OkHttpClient.newCall.implementation = function(request) {
            var url = request.url().toString();
            var method = request.method();

            if (isVideoApi(url)) {
                console.log("\n========== VIDEO API REQUEST ==========");
                console.log("[REQ] " + method + " " + url);
                var headers = request.headers();
                for (var i = 0; i < headers.size(); i++) {
                    console.log("  " + headers.name(i) + ": " + headers.value(i));
                }
                var body = request.body();
                if (body != null) {
                    try {
                        var Buffer = Java.use("okio.Buffer");
                        var buffer = Buffer.$new();
                        body.writeTo(buffer);
                        var rawBytes = buffer.readByteArray();
                        if (isGzip(rawBytes)) {
                            console.log("  BODY-RAW: gzip, " + rawBytes.length + " bytes");
                            var decompressed = decompressGzip(rawBytes);
                            if (decompressed) {
                                console.log("  BODY-JSON: " + decompressed);
                            }
                        } else {
                            console.log("  BODY: " + buffer.readUtf8());
                        }
                    } catch(e) { console.log("  BODY: [error: " + e + "]"); }
                }
                console.log("========== END REQUEST ==========\n");
            }
            return this.newCall(request);
        };
        console.log("[*] OkHttpClient.newCall hooked");
    } catch(e) {}

    // ========== 4. Hook Activity.onResume to detect ShortSeriesActivity and auto-click ==========
    try {
        var Activity = Java.use("android.app.Activity");
        var didClick = false;

        Activity.onResume.implementation = function() {
            var className = this.getClass().getName();
            console.log("[onResume] " + className);
            this.onResume();

            if (className.indexOf("ShortSeriesActivity") >= 0 && !didClick) {
                didClick = true;
                console.log("[*] ShortSeriesActivity.onResume detected! Scheduling click...");
                scheduleClickRetry(0);
            }
        };
        console.log("[*] Activity.onResume hooked (generic)");
    } catch(e) {
        console.log("[-] Activity.onResume hook failed: " + e);
    }

    function dumpViewTree(view, depth) {
        if (view == null || depth > 6) return;
        var className = view.getClass().getName();
        var id = view.getId();
        var idHex = "0x" + id.toString(16);
        var prefix = "";
        for (var i = 0; i < depth; i++) prefix += "  ";
        console.log(prefix + className + " [id=" + idHex + "]");
        try {
            var ViewGroup = Java.use("android.view.ViewGroup");
            var vg = Java.cast(view, ViewGroup);
            var count = vg.getChildCount();
            for (var i = 0; i < count && i < 20; i++) {
                dumpViewTree(vg.getChildAt(i), depth + 1);
            }
        } catch(e) {}
    }

    function findRecyclerViewInHierarchy(view, depth) {
        if (view == null || depth > 12) return null;
        var className = view.getClass().getName();
        if (className.indexOf("RecyclerView") >= 0) {
            return view;
        }
        try {
            var ViewGroup = Java.use("android.view.ViewGroup");
            var vg = Java.cast(view, ViewGroup);
            var count = vg.getChildCount();
            for (var i = 0; i < count; i++) {
                var found = findRecyclerViewInHierarchy(vg.getChildAt(i), depth + 1);
                if (found != null) return found;
            }
        } catch(e) {}
        return null;
    }

    function scheduleClickRetry(attempt) {
        if (attempt >= 2) {
            console.log("[-] Max retries reached");
            return;
        }
        Java.scheduleOnMainThread(function() {
            try {
                // Enumerate all loaded classes containing "player" or "Player"
                console.log("[*] Searching for player classes...");
                Java.enumerateLoadedClasses({
                    onMatch: function(className) {
                        if (className.indexOf("Player") >= 0 || className.indexOf("player") >= 0) {
                            if (className.indexOf("com.dragon") >= 0 || className.indexOf("com.phoenix") >= 0 ||
                                className.indexOf("com.ss") >= 0 || className.indexOf("com.bytedance") >= 0) {
                                console.log("[CLASS] " + className);
                            }
                        }
                    },
                    onComplete: function() {
                        console.log("[*] Class search complete");
                    }
                });

                // Try to find SeriesScrollViewPager and dump page 1 view tree
                Java.choose("com.dragon.read.component.shortvideo.impl.ShortSeriesActivity", {
                    onMatch: function(instance) {
                        var decorView = instance.getWindow().getDecorView();
                        var pagerId = 0x7f1112ce;
                        var viewPager = decorView.findViewById(pagerId);
                        if (viewPager != null) {
                            var ViewPager = Java.use("androidx.viewpager.widget.ViewPager");
                            var vp = Java.cast(viewPager, ViewPager);
                            var currentItem = vp.getCurrentItem();
                            console.log("[*] Current page: " + currentItem);

                            // Try to get child views
                            try {
                                for (var i = 0; i < vp.getChildCount(); i++) {
                                    var child = vp.getChildAt(i);
                                    console.log("[*] VP child " + i + ": " + child.getClass().getName());
                                }
                            } catch(e) {}

                            // Dump current page view tree if not already done
                            if (currentItem >= 0) {
                                console.log("[*] === Page " + currentItem + " View Tree ===");
                                dumpViewTree(decorView, 0);
                                console.log("[*] === End ===");
                            }
                        }
                    },
                    onComplete: function() {}
                });

            } catch(e) {
                console.log("[-] Error: " + e);
            }
        });
    }

    console.log("[*] AutoPlay init complete");
});


