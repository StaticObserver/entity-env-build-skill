# ADIOS2 Build Notes

ADIOS2 is the most complex dependency due to its multi-library dependency chain
(Kokkos + HDF5) and GPU-aware compilation.

## Version Policy

| Profile | ADIOS2 Version | Kokkos Support | CUDA via |
|---------|---------------|----------------|----------|
| legacy  | 2.10.x        | OFF            | n/a      |
| modern  | 2.11.x        | ON             | Kokkos only |

## CMake Options

Baseline (all profiles):
```
-DCMAKE_CXX_EXTENSIONS=OFF
-DCMAKE_POSITION_INDEPENDENT_CODE=TRUE
-DBUILD_SHARED_LIBS=ON
-DADIOS2_USE_Python=OFF
-DADIOS2_USE_Fortran=OFF
-DADIOS2_USE_ZeroMQ=OFF
-DBUILD_TESTING=OFF
-DADIOS2_BUILD_EXAMPLES=OFF
-DADIOS2_USE_HDF5=ON
```

Profile/backend-dependent:
| Condition | Options |
|-----------|---------|
| MPI=ON     | `-DADIOS2_USE_MPI=ON -DADIOS2_HAVE_HDF5_VOL=ON` |
| MPI=OFF    | `-DADIOS2_USE_MPI=OFF -DADIOS2_HAVE_HDF5_VOL=OFF` |
| modern     | `-DADIOS2_USE_Kokkos=ON` |
| cuda + modern | `-DADIOS2_USE_CUDA=OFF` (CUDA goes through Kokkos) |
| cuda + legacy  | `-DADIOS2_USE_CUDA=ON` (direct CUDA, no Kokkos) |

CUDA + modern profile ADDITIONALLY requires:
```
-DCMAKE_CUDA_COMPILER=<cuda_prefix>/bin/nvcc
-DCMAKE_CUDA_ARCHITECTURES=<arch_number>
```
These are needed because ADIOS2+Kokkos triggers CMake `enable_language(CUDA)`.

CMAKE_PREFIX_PATH must include both Kokkos and HDF5 prefixes before ADIOS2 configure,
with Kokkos first (so ADIOS2 finds KokkosConfig.cmake before falling back to non-Kokkos).

## Known Issues

### CUDA Stub Library on Login Nodes
- Symptom: linker error `cannot find -lcuda` or `libcuda.so not found`
- Trigger: Building on login node without GPU drivers (no libcuda.so.1)
- Fix: Add CUDA stubs path to linker flags:
  ```bash
  export LDFLAGS="-L<cuda_prefix>/targets/x86_64-linux/lib/stubs"
  ```
  Or create symlink: `ln -s libcuda.so libcuda.so.1` in stubs directory.
  GPU compute nodes don't need this.

### enable_language(CUDA) Without Required Variables
- Symptom: CMake error "No CMAKE_CUDA_COMPILER could be found"
- Trigger: ADIOS2 with Kokkos CUDA backend triggers CUDA language support
- Fix: Set `-DCMAKE_CUDA_COMPILER=<cuda_prefix>/bin/nvcc` explicitly in cmake configure

### Incomplete cmake --install (Missing Targets Files)
- Symptom: Entity cmake configure fails with "adios2 targets not found"
- Trigger: ADIOS2 `cmake --install` sometimes skips c/cxx targets export files
- Fix: After `cmake --install`, verify and manually copy if needed:
  ```bash
  # Check what's missing
  ls <prefix>/lib64/cmake/adios2/adios2-targets-*.cmake
  # If missing, copy from build tree
  cp <build_dir>/adios2-targets-*.cmake <prefix>/lib64/cmake/adios2/
  ```
  The required files are: `adios2-targets.cmake`, `adios2-targets-release.cmake`,
  `adios2-c-targets.cmake`, `adios2-c-targets-release.cmake`,
  `adios2-cxx-targets.cmake`, `adios2-cxx-targets-release.cmake`.

### GCC libstdc++ ABI Version Mismatch
- Symptom: `undefined reference to std::__cxx11::...` during ADIOS2 link
- Trigger: Mixing GCC versions (old system GCC libstdc++ vs new compiler)
- Fix: Ensure LD_LIBRARY_PATH includes the selected compiler's lib64 directory.
  This is handled by env.sh generation.

### nvcc_wrapper With Wrong Host Compiler
- Symptom: ADIOS2 configure detects wrong host compiler
- Trigger: Kokkos nvcc_wrapper script has stale NVCC_WRAPPER_DEFAULT_COMPILER
- Fix: Patch nvcc_wrapper or create a wrapper script that sets the variable first:
  ```bash
  #!/bin/bash
  export NVCC_WRAPPER_DEFAULT_COMPILER=/path/to/g++
  exec /path/to/kokkos/bin/nvcc_wrapper "$@"
  ```

## Post-Build Validation

Expected install structure:
```
<prefix>/
├── bin/
├── include/
├── lib64/
│   ├── libadios2_c.so
│   ├── libadios2.so
│   └── cmake/adios2/
│       ├── adios2-config.cmake
│       ├── adios2-config-version.cmake
│       ├── adios2-targets.cmake
│       ├── adios2-targets-release.cmake
│       ├── adios2-c-targets.cmake
│       ├── adios2-c-targets-release.cmake
│       ├── adios2-cxx-targets.cmake
│       └── adios2-cxx-targets-release.cmake
```

Verify:
```bash
# CMake config
ls <prefix>/lib64/cmake/adios2/adios2-config.cmake

# Targets files (all 6 must exist)
ls <prefix>/lib64/cmake/adios2/adios2-targets*.cmake \
   <prefix>/lib64/cmake/adios2/adios2-c-targets*.cmake \
   <prefix>/lib64/cmake/adios2/adios2-cxx-targets*.cmake

# Libraries
ls <prefix>/lib64/libadios2_c.so <prefix>/lib64/libadios2.so
```
