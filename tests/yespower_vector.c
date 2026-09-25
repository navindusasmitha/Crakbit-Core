/* Crakbit-owned deterministic yespower vector probe.
 *
 * Input bytes are exactly 0x00..0x4f (80 bytes), matching the serialized size
 * of a Bitcoin-style block header. The output is raw yespower bytes in order.
 */
#include "yespower.h"

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

int main(void)
{
    uint8_t header[80];
    for (size_t i = 0; i < sizeof(header); ++i) {
        header[i] = (uint8_t)i;
    }

    static const uint8_t pers[] = "Crakbit-Core-v0.1";
    const yespower_params_t params = {
        YESPOWER_1_0,
        2048,
        8,
        pers,
        sizeof(pers) - 1,
    };

    yespower_binary_t out;
    if (yespower_tls(header, sizeof(header), &params, &out) != 0) {
        fputs("yespower_tls failed\n", stderr);
        return 1;
    }

    for (size_t i = 0; i < sizeof(out.uc); ++i) {
        printf("%02x", out.uc[i]);
    }
    putchar('\n');
    return 0;
}
