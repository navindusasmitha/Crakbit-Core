cmake_minimum_required(VERSION 3.20)
project(CrakbitCore VERSION 0.1.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

include(FetchContent)

# Consensus dependency: official RandomX upstream, pinned by release tag.
FetchContent_Declare(
  randomx
  GIT_REPOSITORY https://github.com/tevador/RandomX.git
  GIT_TAG v1.2.3
  GIT_SHALLOW TRUE
)
set(RANDOMX_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(RANDOMX_BUILD_BENCHMARKS OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(randomx)

find_package(OpenSSL REQUIRED)

add_executable(crakbitd
  src/main.cpp
  src/core/block.cpp
  src/core/chain.cpp
  src/pow/randomx_pow.cpp
)

target_include_directories(crakbitd PRIVATE
  ${CMAKE_CURRENT_SOURCE_DIR}/src
  ${randomx_SOURCE_DIR}/src
)

target_link_libraries(crakbitd PRIVATE randomx OpenSSL::Crypto)

target_compile_options(crakbitd PRIVATE
  $<$<CXX_COMPILER_ID:GNU,Clang>:-Wall -Wextra -Wpedantic>
)

install(TARGETS crakbitd RUNTIME DESTINATION bin)
