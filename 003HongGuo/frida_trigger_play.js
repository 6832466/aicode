// Frida script: Find RecyclerView adapter and programmatically click episode
Java.perform(function() {
    console.log("[*] Trigger play loaded");

    // Helper: find RecyclerView and click first item
    function clickFirstEpisode() {
        try {
            // Get current activity
            var ActivityThread = Java.use("android.app.ActivityThread");
            var currentActivityThread = ActivityThread.currentActivityThread();
            var activities = currentActivityThread.getApplication().value;

            // Find RecyclerView by id
            var RecyclerView = Java.use("androidx.recyclerview.widget.RecyclerView");

            // Use the activity to find RecyclerView
            var app = Java.use("android.app.ActivityThread").currentApplication();
            var context = app.getApplicationContext();

            console.log("[*] Trying to trigger episode click...");

            // Hook ShortSeriesActivity onCreate/onResume to capture the RecyclerView
            var ShortSeriesActivity = Java.use("com.dragon.read.component.shortvideo.impl.ShortSeriesActivity");

            // Hook onResume to find RecyclerView
            ShortSeriesActivity.onResume.implementation = function() {
                console.log("[*] ShortSeriesActivity.onResume called");
                this.onResume();

                // Give UI time to render, then find RecyclerView
                Java.scheduleOnMainThread(function() {
                    try {
                        // Find RecyclerView through the activity's view hierarchy
                        var window = this.getWindow();
                        var decorView = window.getDecorView();
                        var rootView = decorView.getRootView();

                        // Try to find RecyclerView with id cdq
                        var resources = Java.use("com.phoenix.read.R$id");
                        var cdqId = resources.cdq.value;
                        var recyclerView = rootView.findViewById(cdqId);

                        if (recyclerView != null) {
                            console.log("[*] Found RecyclerView: " + recyclerView);
                            var adapter = recyclerView.getAdapter();
                            console.log("[*] Adapter: " + adapter);
                            console.log("[*] Item count: " + adapter.getItemCount());

                            // Try to get ViewHolder for position 0
                            var viewHolder = recyclerView.findViewHolderForAdapterPosition(0);
                            if (viewHolder != null) {
                                console.log("[*] ViewHolder for pos 0: " + viewHolder);
                                var itemView = viewHolder.itemView;
                                console.log("[*] ItemView: " + itemView);
                                itemView.performClick();
                                console.log("[*] Click performed on episode 1!");
                            } else {
                                console.log("[-] ViewHolder for pos 0 is null, trying scroll...");
                                recyclerView.scrollToPosition(0);
                            }
                        } else {
                            console.log("[-] RecyclerView not found via id cdq");
                        }
                    } catch(e) {
                        console.log("[-] Error finding RecyclerView: " + e);
                    }
                });
            };

            console.log("[*] ShortSeriesActivity.onResume hooked - navigate to series page to trigger");
        } catch(e) {
            console.log("[-] Error: " + e);
        }
    }

    // Try to hook and trigger
    setTimeout(clickFirstEpisode, 2000);
});
