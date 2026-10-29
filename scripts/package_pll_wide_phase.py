"""Package the full routed IS03 + PLL2 /640 build and physical-power software."""
import package_intensity_linearized as package

package.WORK = package.ROOT/'build/phase_range_20261029'
package.OUT = package.ROOT/'build/intensity_IS03_PLL640_R7'
package.RELEASE = 'R7-IS03-PLL640'
if __name__ == '__main__':
    package.main()
