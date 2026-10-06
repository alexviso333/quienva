//  QuienVaLiveActivityPlugin.m
//  ObjC bridge so Capacitor can discover the Swift plugin and its methods.

#import <Foundation/Foundation.h>
#import <Capacitor/Capacitor.h>

CAP_PLUGIN(QuienVaLiveActivityPlugin, "QuienVaLiveActivity",
           CAP_PLUGIN_METHOD(isSupported, CAPPluginReturnPromise);
           CAP_PLUGIN_METHOD(startPlan, CAPPluginReturnPromise);
           CAP_PLUGIN_METHOD(updatePlan, CAPPluginReturnPromise);
           CAP_PLUGIN_METHOD(endPlan, CAPPluginReturnPromise);
)
