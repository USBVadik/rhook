/* Read-only host snapshot. No process enumeration, credentials or network.
 * XNU free_count ALREADY includes speculative_count; never add them together.
 */
#include <mach/mach.h>
#include <mach/vm_statistics.h>
#include <sys/sysctl.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <time.h>

static uint64_t ns(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) exit(2);
    return (uint64_t)t.tv_sec*1000000000 + t.tv_nsec;
}
static void read_value(const char *name, void *value, size_t size) {
    size_t actual = size;
    if (sysctlbyname(name, value, &actual, NULL, 0) || actual != size) {
        fprintf(stderr, "sysctl failed: %s\n", name); exit(2);
    }
}
int main(void) {
#if !defined(__APPLE__) || !defined(__arm64__)
    return 2;
#else
    uint64_t began=ns(), physical=0;
    int pressure0=0, pressure1=0;
    struct xsw_usage swap0={0}, swap1={0};
    char boot0[128]={0}, boot1[128]={0}; size_t n0=sizeof boot0, n1=sizeof boot1;
    if (sysctlbyname("kern.bootsessionuuid", boot0, &n0, NULL, 0)) return 2;
    read_value("hw.memsize", &physical, sizeof physical);
    read_value("kern.memorystatus_vm_pressure_level", &pressure0, sizeof pressure0);
    read_value("vm.swapusage", &swap0, sizeof swap0);
    vm_statistics64_data_t vm={0}; mach_msg_type_number_t count=HOST_VM_INFO64_COUNT;
    vm_size_t page=0; mach_port_t host=mach_host_self();
    kern_return_t a=host_page_size(host, &page);
    kern_return_t b=host_statistics64(host, HOST_VM_INFO64, (host_info64_t)&vm, &count);
    mach_port_deallocate(mach_task_self(), host);
    if (a != KERN_SUCCESS || b != KERN_SUCCESS || count != HOST_VM_INFO64_COUNT) return 2;
    read_value("vm.swapusage", &swap1, sizeof swap1);
    read_value("kern.memorystatus_vm_pressure_level", &pressure1, sizeof pressure1);
    if (sysctlbyname("kern.bootsessionuuid", boot1, &n1, NULL, 0)) return 2;
    if (!n0 || n0>sizeof boot0 || !n1 || n1>sizeof boot1 || boot0[n0-1] || boot1[n1-1]) return 2;
    /* UUID alphabet only; reject surprises rather than escaping arbitrary data. */
    for (size_t i=0; boot0[i]; ++i)
        if (!((boot0[i]>='0' && boot0[i]<='9') || (boot0[i]>='a' && boot0[i]<='f') ||
              (boot0[i]>='A' && boot0[i]<='F') || boot0[i]=='-')) return 2;
    if (n0 != n1 || __builtin_strcmp(boot0, boot1)) return 2;
    printf("{\"source\":\"DARWIN_HOST_VM64/1\",\"platform\":\"darwin-arm64\","
           "\"boot\":\"%s\",\"beganNs\":%llu,\"endedNs\":%llu,\"physicalBytes\":%llu,"
           "\"pageBytes\":%llu,\"freePages\":%llu,\"speculativePages\":%llu,"
           "\"pressureBefore\":%d,\"pressureAfter\":%d,\"swapOutPages\":%llu,"
           "\"swapUsedBeforeBytes\":%llu,\"swapUsedBytes\":%llu}\n", boot0,
           (unsigned long long)began, (unsigned long long)ns(), (unsigned long long)physical,
           (unsigned long long)page, (unsigned long long)vm.free_count,
           (unsigned long long)vm.speculative_count, pressure0, pressure1,
           (unsigned long long)vm.swapouts, (unsigned long long)swap0.xsu_used,
           (unsigned long long)swap1.xsu_used);
    return 0;
#endif
}
