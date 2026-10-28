/* Read-only macOS arm64 VM telemetry. No allocation workload or process scan. */
#include <mach/mach.h>
#include <mach/vm_statistics.h>
#include <sys/sysctl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static uint64_t ns(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) exit(2);
    return (uint64_t)t.tv_sec * 1000000000 + t.tv_nsec;
}

static void read_value(const char *name, void *value, size_t size) {
    size_t actual = size;
    if (sysctlbyname(name, value, &actual, NULL, 0) || actual != size) {
        fprintf(stderr, "sysctl unavailable: %s\n", name);
        exit(2);
    }
}

int main(void) {
#if !defined(__APPLE__) || !defined(__arm64__)
    return 2;
#else
    uint64_t began = ns(), physical = 0;
    int pressure0 = 0, pressure1 = 0;
    struct xsw_usage swap0 = {0}, swap1 = {0};
    char boot0[128] = {0}, boot1[128] = {0};
    size_t n0 = sizeof boot0, n1 = sizeof boot1;
    if (sysctlbyname("kern.bootsessionuuid", boot0, &n0, NULL, 0)) return 2;
    read_value("hw.memsize", &physical, sizeof physical);
    read_value("kern.memorystatus_vm_pressure_level", &pressure0, sizeof pressure0);
    read_value("vm.swapusage", &swap0, sizeof swap0);
    vm_statistics64_data_t vm = {0};
    mach_msg_type_number_t count = HOST_VM_INFO64_COUNT;
    vm_size_t page = 0;
    mach_port_t host = mach_host_self();
    kern_return_t a = host_page_size(host, &page);
    kern_return_t b = host_statistics64(host, HOST_VM_INFO64, (host_info64_t)&vm, &count);
    mach_port_deallocate(mach_task_self(), host);
    if (a != KERN_SUCCESS || b != KERN_SUCCESS || count < HOST_VM_INFO64_REV1_COUNT) return 2;
    read_value("vm.swapusage", &swap1, sizeof swap1);
    read_value("kern.memorystatus_vm_pressure_level", &pressure1, sizeof pressure1);
    if (sysctlbyname("kern.bootsessionuuid", boot1, &n1, NULL, 0)) return 2;
    if (!n0 || n0 > sizeof boot0 || !n1 || n1 > sizeof boot1 ||
        boot0[n0 - 1] || boot1[n1 - 1] || n0 != n1 || strcmp(boot0, boot1)) return 2;
    for (size_t i = 0; boot0[i]; i++) {
        char c = boot0[i];
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') ||
              (c >= 'A' && c <= 'F') || c == '-')) return 2;
    }
    struct { const char *name; uint64_t value; } values[] = {
        {"beganNs", began}, {"endedNs", ns()}, {"physicalBytes", physical},
        {"pageBytes", page}, {"freePages", vm.free_count},
        {"speculativePages", vm.speculative_count}, {"inactivePages", vm.inactive_count},
        {"activePages", vm.active_count}, {"fileBackedPages", vm.external_page_count},
        {"anonymousPages", vm.internal_page_count}, {"purgeablePages", vm.purgeable_count},
        {"wiredPages", vm.wire_count}, {"compressorPages", vm.compressor_page_count},
        {"compressedLogicalPages", vm.total_uncompressed_pages_in_compressor},
        {"compressions", vm.compressions}, {"decompressions", vm.decompressions},
        {"pressureBefore", (uint64_t)pressure0}, {"pressureAfter", (uint64_t)pressure1},
        {"swapInPages", vm.swapins}, {"swapOutPages", vm.swapouts},
        {"swapUsedBeforeBytes", swap0.xsu_used}, {"swapUsedBytes", swap1.xsu_used}
    };
    printf("{\"source\":\"DARWIN_HOST_VM64/3\",\"platform\":\"darwin-arm64\",\"boot\":\"%s\"", boot0);
    for (size_t i = 0; i < sizeof values / sizeof values[0]; i++)
        printf(",\"%s\":%llu", values[i].name, (unsigned long long)values[i].value);
    puts("}");
    return ferror(stdout) ? 2 : 0;
#endif
}
